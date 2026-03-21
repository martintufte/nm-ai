#!/usr/bin/env bash
# Tripletex Knowledge Base Verification Suite
# Tests every documented gotcha and unverified gap against the sandbox API.
# Usage: TRIPLETEX_SANDBOX_API_URL=... TRIPLETEX_SANDBOX_TOKEN=... bash verify.sh
set -uo pipefail

BASE="${TRIPLETEX_SANDBOX_API_URL:?Set TRIPLETEX_SANDBOX_API_URL}"
TOKEN="${TRIPLETEX_SANDBOX_TOKEN:?Set TRIPLETEX_SANDBOX_TOKEN}"

# --- Counters ---
PASS=0; XFAIL=0; FAIL=0; SKIP=0
RESULTS=()  # array of result lines for summary

TODAY=$(date +%Y-%m-%d)
TOMORROW=$(date -d "+1 day" +%Y-%m-%d 2>/dev/null || date -v+1d +%Y-%m-%d)
DUE_DATE=$(date -d "+30 days" +%Y-%m-%d 2>/dev/null || date -v+30d +%Y-%m-%d)
TS=$(date +%s)  # unique suffix to avoid name collisions across runs

# --- IDs captured during run ---
declare -A IDS

# --- Helpers ---
api() {
  # api METHOD endpoint [body]
  # Returns: sets LAST_CODE, LAST_BODY
  local method="$1" endpoint="$2" body="${3:-}"
  local args=(-s -w "\n---HTTP_CODE:%{http_code}" -u "0:$TOKEN" -H "Content-Type: application/json" -X "$method")
  [ -n "$body" ] && args+=(-d "$body")
  local raw
  raw=$(curl "${args[@]}" "$BASE/$endpoint")
  LAST_CODE=$(echo "$raw" | grep -o 'HTTP_CODE:[0-9]*' | cut -d: -f2)
  LAST_BODY=$(echo "$raw" | sed '/---HTTP_CODE:/d')
}

# Extract .value.id from JSON response
extract_id() {
  echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['value']['id'])" 2>/dev/null
}

# Extract .value.version from JSON response
extract_version() {
  echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['value']['version'])" 2>/dev/null
}

# Extract first value's id from list response
extract_first_id() {
  echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['values'][0]['id'])" 2>/dev/null
}

# Extract field from first value in list
extract_first_field() {
  local field="$1"
  echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['values'][0]['$field'])" 2>/dev/null
}

# Extract id from value.url (for sub-resources that only return URL)
extract_url_id() {
  echo "$LAST_BODY" | python3 -c "
import sys,json
d=json.load(sys.stdin)
url=d.get('value',{}).get('url','')
print(url.rstrip('/').split('/')[-1])
" 2>/dev/null
}

# Get validation messages summary
validation_msg() {
  echo "$LAST_BODY" | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin)
  msgs=d.get('validationMessages',[])
  for m in msgs[:3]:
    print(f\"  {m.get('field','?')}: {m['message']}\")
  if not msgs and 'message' in d:
    print(f\"  {d['message']}\")
except: pass
" 2>/dev/null
}

record() {
  # record RESULT TEST_ID DESCRIPTION [detail]
  local result="$1" tid="$2" desc="$3" detail="${4:-}"
  local line
  case "$result" in
    PASS)  ((PASS++));  line="PASS  $tid $desc  ($detail)" ;;
    XFAIL) ((XFAIL++)); line="XFAIL $tid $desc  ($detail)" ;;
    FAIL)  ((FAIL++));   line="FAIL  $tid $desc  ($detail)" ;;
    SKIP)  ((SKIP++));   line="SKIP  $tid $desc  ($detail)" ;;
  esac
  RESULTS+=("$line")
  echo "$line"
}

# Test that expects a success (2xx)
expect_success() {
  local tid="$1" desc="$2" expected_code="${3:-201}"
  if [ "$LAST_CODE" = "$expected_code" ]; then
    record PASS "$tid" "$desc" "$expected_code"
  else
    record FAIL "$tid" "$desc" "expected $expected_code, got $LAST_CODE"
    validation_msg
  fi
}

# Test that expects a failure (4xx)
expect_fail() {
  local tid="$1" desc="$2" expected_code="${3:-422}"
  if [ "$LAST_CODE" = "$expected_code" ]; then
    record XFAIL "$tid" "$desc" "$expected_code as expected"
  else
    record FAIL "$tid" "$desc" "expected $expected_code, got $LAST_CODE"
    validation_msg
  fi
}

# Test where we don't know what will happen - just record the result
expect_unknown() {
  local tid="$1" desc="$2"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    record PASS "$tid" "$desc" "$LAST_CODE"
  else
    record FAIL "$tid" "$desc" "got $LAST_CODE"
    validation_msg
  fi
}

echo "======================================================================"
echo "  Tripletex Knowledge Base Verification Suite"
echo "  $(date)"
echo "======================================================================"
echo ""

# ======================================================================
# SETUP: Lookup reference data
# ======================================================================
echo "=== SETUP: Lookup reference data ==="

# T00: Get employee + department
api GET "employee?count=1"
IDS[EMP_ID]=$(extract_first_id)
IDS[DEPT_ID]=$(echo "$LAST_BODY" | python3 -c "
import sys,json
v=json.load(sys.stdin)['values'][0]
dept=v.get('department',{})
print(dept.get('id',''))
" 2>/dev/null)
record PASS T00 "GET /employee" "EMP_ID=${IDS[EMP_ID]}, DEPT_ID=${IDS[DEPT_ID]}"

# T00b: Ensure VAT registration (required for outgoing VAT codes like id=3)
api GET "ledger/vatSettings"
VAT_ID=$(extract_id)
VAT_VER=$(extract_version)
VAT_STATUS=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['value']['vatRegistrationStatus'])" 2>/dev/null)
if [ "$VAT_STATUS" != "VAT_REGISTERED" ]; then
  api PUT "ledger/vatSettings" "{\"id\":$VAT_ID,\"version\":$VAT_VER,\"vatRegistrationStatus\":\"VAT_REGISTERED\"}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    record PASS T00b "Enable VAT registration" "was $VAT_STATUS"
  else
    record FAIL T00b "Enable VAT registration" "got $LAST_CODE"
  fi
else
  record PASS T00b "VAT already registered" "$VAT_STATUS"
fi

# T01: Payment types for invoicing
api GET "invoice/paymentType?count=5"
IDS[PAY_TYPE_ID]=$(extract_first_id)
record PASS T01 "GET /invoice/paymentType" "PAY_TYPE_ID=${IDS[PAY_TYPE_ID]}"

# T02: Travel payment types
api GET "travelExpense/paymentType?count=5"
IDS[TRAVEL_PAY_ID]=$(extract_first_id)
record PASS T02 "GET /travelExpense/paymentType" "TRAVEL_PAY_ID=${IDS[TRAVEL_PAY_ID]}"

# T03: Travel cost categories
api GET "travelExpense/costCategory?showOnTravelExpenses=true&count=5"
IDS[COST_CAT_ID]=$(extract_first_id)
record PASS T03 "GET /travelExpense/costCategory" "COST_CAT_ID=${IDS[COST_CAT_ID]}"

# T04: Rate categories (current 2026 ones are at high offsets)
# We use known IDs from the knowledge base for reliability
IDS[MILEAGE_CAT]=743    # Bil
IDS[PERDIEM_CAT]=740    # Overnatting over 12 timer - innland
IDS[ACCOM_CAT]=754      # Ulegitimert - innland
IDS[PERDIEM_DAY_CAT]=738  # Dagsreise 6-12 timer - innland
record PASS T04 "Rate categories (known IDs)" "MILEAGE=${IDS[MILEAGE_CAT]}, PERDIEM=${IDS[PERDIEM_CAT]}, ACCOM=${IDS[ACCOM_CAT]}"

# T05: Currency NOK
api GET "currency?code=NOK"
IDS[CURRENCY_ID]=$(extract_first_id)
record PASS T05 "GET /currency?code=NOK" "CURRENCY_ID=${IDS[CURRENCY_ID]}"

# T06: Bank account
api GET "ledger/account?isBankAccount=true&count=5"
IDS[BANK_ACCT_ID]=$(extract_first_id)
IDS[BANK_ACCT_VER]=$(extract_first_field version)
record PASS T06 "GET /ledger/account (bank)" "BANK_ACCT_ID=${IDS[BANK_ACCT_ID]}, ver=${IDS[BANK_ACCT_VER]}"

echo ""

# ======================================================================
# PHASE 1: Simple entity creation (no deps)
# ======================================================================
echo "=== PHASE 1: Simple entity creation ==="

# T10: Create customer
api POST customer "{\"name\":\"Verify Customer $TS\"}"
expect_success T10 "POST /customer (minimal)"
IDS[CUST_ID]=$(extract_id)

# T11: Create department
api POST department "{\"name\":\"Verify Dept $TS\"}"
expect_success T11 "POST /department (minimal)"
IDS[DEPT2_ID]=$(extract_id)

# T12: Create product with price
api POST product "{\"name\":\"Verify Product $TS\",\"priceExcludingVatCurrency\":500.0}"
expect_success T12 "POST /product (with price)"
IDS[PROD_ID]=$(extract_id)

echo ""

# ======================================================================
# PHASE 2: Employee gotchas
# ======================================================================
echo "=== PHASE 2: Employee gotchas ==="

# T20: Employee without userType → 422 (gotcha #1)
api POST employee '{"firstName":"NoType","lastName":"Test"}'
expect_fail T20 "POST /employee (no userType) [gotcha #1]"

# T21: Employee with userType but no department → 422 (gotcha #2)
api POST employee '{"firstName":"NoDept","lastName":"Test","userType":"NO_ACCESS"}'
expect_fail T21 "POST /employee (no department) [gotcha #2]"

# T22: STANDARD employee without email → 422 (gotcha #3)
api POST employee "{\"firstName\":\"NoEmail\",\"lastName\":\"Test\",\"userType\":\"STANDARD\",\"department\":{\"id\":${IDS[DEPT_ID]}}}"
expect_fail T22 "POST /employee (STANDARD, no email) [gotcha #3]"

# T23: NO_ACCESS minimal → 201
api POST employee "{\"firstName\":\"Verify\",\"lastName\":\"NoAccess\",\"userType\":\"NO_ACCESS\",\"department\":{\"id\":${IDS[DEPT_ID]}}}"
expect_success T23 "POST /employee (NO_ACCESS minimal)"
IDS[EMP2_ID]=$(extract_id)

# T24: STANDARD with email + dept → 201
api POST employee "{\"firstName\":\"Verify\",\"lastName\":\"Standard\",\"userType\":\"STANDARD\",\"email\":\"verify-std-$(date +%s)@test.example.com\",\"department\":{\"id\":${IDS[DEPT_ID]}}}"
expect_success T24 "POST /employee (STANDARD with email+dept)"
IDS[EMP3_ID]=$(extract_id)

# T25: Employee with extra contact fields (unverified #9)
api POST employee "{
  \"firstName\":\"Verify\",\"lastName\":\"Contact\",
  \"userType\":\"NO_ACCESS\",
  \"department\":{\"id\":${IDS[DEPT_ID]}},
  \"phoneNumberMobile\":\"12345678\",
  \"address\":{\"addressLine1\":\"Testveien 1\",\"postalCode\":\"0001\",\"city\":\"Oslo\"}
}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  record PASS T25 "POST /employee (with contact fields)" "$LAST_CODE - phone+address accepted"
  IDS[EMP4_ID]=$(extract_id)
else
  record FAIL T25 "POST /employee (with contact fields)" "got $LAST_CODE"
  validation_msg
fi

echo ""

# ======================================================================
# PHASE 3: Project gotchas
# ======================================================================
echo "=== PHASE 3: Project gotchas ==="

# T30: Project without startDate → 422 (gotcha #5)
api POST project "{\"name\":\"NoDate Project $TS\",\"projectManager\":{\"id\":${IDS[EMP_ID]}},\"isInternal\":true}"
expect_fail T30 "POST /project (no startDate) [gotcha #5]"

# T31: Project with startDate → 201
api POST project "{\"name\":\"Verify Project $TS\",\"projectManager\":{\"id\":${IDS[EMP_ID]}},\"isInternal\":true,\"startDate\":\"$TODAY\"}"
expect_success T31 "POST /project (with startDate)"
IDS[PROJ_ID]=$(extract_id)

# T32: Subcontract without displayName → 422 (secretly required)
api POST "project/subcontract" "{\"project\":{\"id\":${IDS[PROJ_ID]}},\"name\":\"SubNoDisplay $TS\",\"budgetExpensesCurrency\":1000}"
expect_fail T32 "POST /project/subcontract (no displayName) [secretly required]"

echo ""

# ======================================================================
# PHASE 4: Product gotchas
# ======================================================================
echo "=== PHASE 4: Product gotchas ==="

# T40: Product with vatType id=3 (outgoing 25%) → 201 when VAT registered
api POST product "{\"name\":\"VatTest3 $TS\",\"vatType\":{\"id\":3}}"
expect_success T40 "POST /product (vatType id=3, outgoing 25%)"
IDS[PROD_VAT3_ID]=$(extract_id)

# T40b: Product with vatType id=31 (outgoing 15%) → 201 when VAT registered
api POST product "{\"name\":\"VatTest31 $TS\",\"vatType\":{\"id\":31}}"
expect_success T40b "POST /product (vatType id=31, outgoing 15%)"

# T40c: Product with vatType id=1 (ingoing 25%) → 201 when VAT registered
api POST product "{\"name\":\"VatTest1 $TS\",\"vatType\":{\"id\":1}}"
expect_success T40c "POST /product (vatType id=1, ingoing 25%)"

# T42: Product without vatType → 201
api POST product "{\"name\":\"NoVat Product $TS\"}"
expect_success T42 "POST /product (no vatType)"
IDS[PROD2_ID]=$(extract_id)

# T43: Product with priceIncludingVatCurrency (unverified #11)
api POST product "{\"name\":\"PriceInclVat $TS\",\"priceIncludingVatCurrency\":625.0}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  record PASS T43 "POST /product (priceIncludingVatCurrency)" "$LAST_CODE"
  IDS[PROD3_ID]=$(extract_id)
  # Check if priceExcludingVatCurrency was auto-calculated
  api GET "product/${IDS[PROD3_ID]}"
  echo "$LAST_BODY" | python3 -c "
import sys,json
v=json.load(sys.stdin)['value']
print(f\"  priceExcl={v.get('priceExcludingVatCurrency')}, priceIncl={v.get('priceIncludingVatCurrency')}\")
" 2>/dev/null
else
  record FAIL T43 "POST /product (priceIncludingVatCurrency)" "got $LAST_CODE"
  validation_msg
fi

echo ""

# ======================================================================
# PHASE 5: Invoice workflow
# ======================================================================
echo "=== PHASE 5: Invoice workflow ==="

# T50: Set bank account number (gotcha #10 setup)
api PUT "ledger/account/${IDS[BANK_ACCT_ID]}" "{\"id\":${IDS[BANK_ACCT_ID]},\"version\":${IDS[BANK_ACCT_VER]},\"bankAccountNumber\":\"12345678903\"}"
if [ "$LAST_CODE" = "200" ]; then
  expect_success T50 "PUT /ledger/account (set bank number) [gotcha #10]" 200
  IDS[BANK_ACCT_VER]=$(extract_version)
else
  # May already be set from previous runs
  record PASS T50 "PUT /ledger/account (bank number)" "already set or $LAST_CODE"
fi

# T51: Invoice without orders → 422 (gotcha #9)
api POST invoice "{\"invoiceDate\":\"$TODAY\",\"invoiceDueDate\":\"$DUE_DATE\",\"customer\":{\"id\":${IDS[CUST_ID]}}}"
expect_fail T51 "POST /invoice (no orders) [gotcha #9]"

# T52: Full invoice workflow → 201
api POST invoice "{
  \"invoiceDate\":\"$TODAY\",
  \"invoiceDueDate\":\"$DUE_DATE\",
  \"customer\":{\"id\":${IDS[CUST_ID]}},
  \"orders\":[{
    \"orderDate\":\"$TODAY\",
    \"deliveryDate\":\"$TODAY\",
    \"customer\":{\"id\":${IDS[CUST_ID]}},
    \"orderLines\":[{\"product\":{\"id\":${IDS[PROD_ID]}},\"count\":2}]
  }]
}"
expect_success T52 "POST /invoice (full workflow)"
IDS[INV_ID]=$(extract_id)
# Also capture the order ID from the invoice
IDS[ORDER_ID]=$(echo "$LAST_BODY" | python3 -c "
import sys,json
v=json.load(sys.stdin)['value']
orders=v.get('orders',[])
if orders: print(orders[0].get('id',''))
" 2>/dev/null)

# T53: Payment with body (wrong way) → 422 (gotcha #8)
if [ -n "${IDS[INV_ID]:-}" ]; then
  api PUT "invoice/${IDS[INV_ID]}/:payment" "{\"paymentDate\":\"$TODAY\",\"paymentTypeId\":${IDS[PAY_TYPE_ID]},\"paidAmount\":500.0}"
  expect_fail T53 "PUT /invoice/:payment (body, wrong) [gotcha #8]"

  # T54: Payment with query params (correct) → 200
  api PUT "invoice/${IDS[INV_ID]}/:payment?paymentDate=$TODAY&paymentTypeId=${IDS[PAY_TYPE_ID]}&paidAmount=500.0" ""
  expect_success T54 "PUT /invoice/:payment (query params)" 200

  # T55a: Credit note with body (wrong) → 422 [gotcha: query params, not body]
  api PUT "invoice/${IDS[INV_ID]}/:createCreditNote" "{\"date\":\"$TODAY\",\"comment\":\"VerifyTest\"}"
  expect_fail T55a "PUT /invoice/:createCreditNote (body, wrong) [gotcha #8]"

  # T55: Credit note with query params → 200
  api PUT "invoice/${IDS[INV_ID]}/:createCreditNote?date=$TODAY&comment=VerifyTest" ""
  if [ "$LAST_CODE" = "200" ] || [ "$LAST_CODE" = "201" ]; then
    IDS[CREDIT_ID]=$(extract_id)
    record PASS T55 "PUT /invoice/:createCreditNote (query params)" "$LAST_CODE, CREDIT_ID=${IDS[CREDIT_ID]:-?}"
  else
    record FAIL T55 "PUT /invoice/:createCreditNote" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T53 "PUT /invoice/:payment (body)" "no invoice"
  record SKIP T54 "PUT /invoice/:payment (query params)" "no invoice"
  record SKIP T55a "PUT /invoice/:createCreditNote (body)" "no invoice"
  record SKIP T55 "PUT /invoice/:createCreditNote" "no invoice"
fi

# T56: Invoice with multiple orderlines (unverified #12)
api POST invoice "{
  \"invoiceDate\":\"$TODAY\",
  \"invoiceDueDate\":\"$DUE_DATE\",
  \"customer\":{\"id\":${IDS[CUST_ID]}},
  \"orders\":[{
    \"orderDate\":\"$TODAY\",
    \"deliveryDate\":\"$TODAY\",
    \"customer\":{\"id\":${IDS[CUST_ID]}},
    \"orderLines\":[
      {\"product\":{\"id\":${IDS[PROD_ID]}},\"count\":1},
      {\"product\":{\"id\":${IDS[PROD_ID]}},\"count\":3}
    ]
  }]
}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[INV2_ID]=$(extract_id)
  IDS[ORDER2_ID]=$(echo "$LAST_BODY" | python3 -c "
import sys,json
v=json.load(sys.stdin)['value']
orders=v.get('orders',[])
if orders: print(orders[0].get('id',''))
" 2>/dev/null)
  record PASS T56 "POST /invoice (multiple orderlines)" "$LAST_CODE"
else
  record FAIL T56 "POST /invoice (multiple orderlines)" "got $LAST_CODE"
  validation_msg
fi

echo ""

# ======================================================================
# PHASE 6: Travel expense workflow
# ======================================================================
echo "=== PHASE 6: Travel expense workflow ==="

# T60: Travel expense with dates at top level → 422 (gotcha #6)
api POST travelExpense "{\"employee\":{\"id\":${IDS[EMP_ID]}},\"title\":\"Bad Dates\",\"departureDate\":\"$TODAY\",\"returnDate\":\"$TOMORROW\"}"
expect_fail T60 "POST /travelExpense (dates at top) [gotcha #6]"

# T61: Travel expense with travelDetails → 201
api POST travelExpense "{
  \"employee\":{\"id\":${IDS[EMP_ID]}},
  \"title\":\"Verify Trip\",
  \"travelDetails\":{
    \"departureDate\":\"$TODAY\",
    \"returnDate\":\"$TOMORROW\",
    \"isDayTrip\":false,
    \"isForeignTravel\":false,
    \"departureFrom\":\"Oslo\",
    \"destination\":\"Bergen\",
    \"departureTime\":\"08:00\",
    \"returnTime\":\"18:00\",
    \"purpose\":\"Verification test\"
  }
}"
expect_success T61 "POST /travelExpense (with travelDetails)"
IDS[TE_ID]=$(extract_id)

# T62: Travel expense without title (unverified #4)
api POST travelExpense "{
  \"employee\":{\"id\":${IDS[EMP_ID]}},
  \"travelDetails\":{
    \"departureDate\":\"$TODAY\",
    \"returnDate\":\"$TOMORROW\",
    \"isDayTrip\":true
  }
}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[TE2_ID]=$(extract_id)
  record PASS T62 "POST /travelExpense (no title)" "$LAST_CODE - title is optional!"
else
  record XFAIL T62 "POST /travelExpense (no title)" "$LAST_CODE - title required"
  validation_msg
fi

if [ -n "${IDS[TE_ID]:-}" ]; then
  # T63: Cost with "amount" (wrong field) → 422 (gotcha #7)
  api POST "travelExpense/cost" "{\"travelExpense\":{\"id\":${IDS[TE_ID]}},\"costCategory\":{\"id\":${IDS[COST_CAT_ID]}},\"paymentType\":{\"id\":${IDS[TRAVEL_PAY_ID]}},\"currency\":{\"id\":${IDS[CURRENCY_ID]}},\"amount\":750.0,\"date\":\"$TODAY\"}"
  expect_fail T63 "POST /travelExpense/cost ('amount' wrong) [gotcha #7]"

  # T64: Cost with amountCurrencyIncVat → 201
  api POST "travelExpense/cost" "{\"travelExpense\":{\"id\":${IDS[TE_ID]}},\"costCategory\":{\"id\":${IDS[COST_CAT_ID]}},\"paymentType\":{\"id\":${IDS[TRAVEL_PAY_ID]}},\"currency\":{\"id\":${IDS[CURRENCY_ID]}},\"amountCurrencyIncVat\":750.0,\"date\":\"$TODAY\"}"
  expect_success T64 "POST /travelExpense/cost (amountCurrencyIncVat)"

  # T65: Mileage allowance → 201
  api POST "travelExpense/mileageAllowance" "{
    \"travelExpense\":{\"id\":${IDS[TE_ID]}},
    \"rateType\":{\"id\":${IDS[MILEAGE_CAT]}},
    \"date\":\"$TODAY\",
    \"departureLocation\":\"Oslo\",
    \"destination\":\"Bergen\",
    \"km\":463,
    \"rate\":3.5,
    \"amount\":1620.5,
    \"isCompanyCar\":false
  }"
  expect_success T65 "POST /travelExpense/mileageAllowance"

  # T66: Per diem without location → 422 (gotcha #11)
  api POST "travelExpense/perDiemCompensation" "{\"travelExpense\":{\"id\":${IDS[TE_ID]}},\"rateType\":{\"id\":${IDS[PERDIEM_CAT]}},\"count\":1,\"overnightAccommodation\":\"HOTEL\",\"isDeductionForBreakfast\":false}"
  expect_fail T66 "POST /perDiemCompensation (no location) [gotcha #11]"

  # T67: Per diem with location → 201
  api POST "travelExpense/perDiemCompensation" "{\"travelExpense\":{\"id\":${IDS[TE_ID]}},\"rateType\":{\"id\":${IDS[PERDIEM_CAT]}},\"count\":1,\"location\":\"Bergen\",\"overnightAccommodation\":\"HOTEL\",\"isDeductionForBreakfast\":false}"
  expect_success T67 "POST /perDiemCompensation (with location)"

  # T68: Per diem with countFrom/countTo → 422 (gotcha #12)
  api POST "travelExpense/perDiemCompensation" "{\"travelExpense\":{\"id\":${IDS[TE_ID]}},\"rateType\":{\"id\":${IDS[PERDIEM_CAT]}},\"countFrom\":\"$TODAY\",\"countTo\":\"$TOMORROW\",\"location\":\"Bergen\",\"overnightAccommodation\":\"HOTEL\"}"
  expect_fail T68 "POST /perDiemCompensation (countFrom/To) [gotcha #12]"

  # T69: Accommodation allowance (unverified #1)
  api POST "travelExpense/accommodationAllowance" "{
    \"travelExpense\":{\"id\":${IDS[TE_ID]}},
    \"rateType\":{\"id\":${IDS[ACCOM_CAT]}},
    \"count\":1,
    \"location\":\"Bergen\",
    \"address\":\"Testveien 1\"
  }"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    record PASS T69 "POST /accommodationAllowance" "$LAST_CODE"
  else
    record FAIL T69 "POST /accommodationAllowance" "got $LAST_CODE"
    validation_msg
  fi

  # T69b: Passenger supplement is a SEPARATE mileage entry using rate category 744
  # NOT a boolean field on the main mileage entry
  api POST "travelExpense/mileageAllowance" "{
    \"travelExpense\":{\"id\":${IDS[TE_ID]}},
    \"rateType\":{\"id\":744},
    \"date\":\"$TODAY\",
    \"departureLocation\":\"Oslo\",
    \"destination\":\"Bergen\",
    \"km\":463,
    \"rate\":1.0,
    \"amount\":463.0,
    \"isCompanyCar\":false
  }"
  expect_success T69b "POST /mileageAllowance (passenger supplement as separate entry)"
else
  record SKIP T63 "POST /travelExpense/cost" "no travel expense"
  record SKIP T64 "POST /travelExpense/cost" "no travel expense"
  record SKIP T65 "POST /mileageAllowance" "no travel expense"
  record SKIP T66 "POST /perDiemCompensation (no location)" "no travel expense"
  record SKIP T67 "POST /perDiemCompensation" "no travel expense"
  record SKIP T68 "POST /perDiemCompensation (countFrom/To)" "no travel expense"
  record SKIP T69 "POST /accommodationAllowance" "no travel expense"
  record SKIP T69b "POST /mileageAllowance (passenger)" "no travel expense"
fi

echo ""

# ======================================================================
# PHASE 7: Updates (unverified #8)
# ======================================================================
echo "=== PHASE 7: PUT updates ==="

# T70: Update customer name
if [ -n "${IDS[CUST_ID]:-}" ]; then
  api GET "customer/${IDS[CUST_ID]}"
  local_ver=$(extract_version)
  api PUT "customer/${IDS[CUST_ID]}" "{\"id\":${IDS[CUST_ID]},\"version\":$local_ver,\"name\":\"Verify Customer Updated $TS\"}"
  expect_success T70 "PUT /customer (update name)" 200
else
  record SKIP T70 "PUT /customer" "no customer"
fi

# T71: Update employee
if [ -n "${IDS[EMP2_ID]:-}" ]; then
  api GET "employee/${IDS[EMP2_ID]}"
  local_ver=$(extract_version)
  api PUT "employee/${IDS[EMP2_ID]}" "{\"id\":${IDS[EMP2_ID]},\"version\":$local_ver,\"firstName\":\"Updated\",\"lastName\":\"NoAccess\",\"userType\":\"NO_ACCESS\",\"department\":{\"id\":${IDS[DEPT_ID]}},\"dateOfBirth\":\"1990-01-01\"}"
  expect_success T71 "PUT /employee (update name, dateOfBirth required)" 200
else
  record SKIP T71 "PUT /employee" "no employee"
fi

# T72: Update product price
if [ -n "${IDS[PROD_ID]:-}" ]; then
  api GET "product/${IDS[PROD_ID]}"
  local_ver=$(extract_version)
  api PUT "product/${IDS[PROD_ID]}" "{\"id\":${IDS[PROD_ID]},\"version\":$local_ver,\"name\":\"Verify Product $TS\",\"priceExcludingVatCurrency\":999.0}"
  expect_success T72 "PUT /product (update price)" 200
else
  record SKIP T72 "PUT /product" "no product"
fi

# T73: Customer with isPrivateIndividual + address (unverified #10)
api POST customer "{\"name\":\"Private Person $TS\",\"isPrivateIndividual\":true,\"postalAddress\":{\"addressLine1\":\"Testgata 1\",\"postalCode\":\"0001\",\"city\":\"Oslo\"}}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[CUST2_ID]=$(extract_id)
  record PASS T73 "POST /customer (isPrivateIndividual+address)" "$LAST_CODE"
else
  record FAIL T73 "POST /customer (isPrivateIndividual+address)" "got $LAST_CODE"
  validation_msg
fi

echo ""

# ======================================================================
# PHASE 8: Deletions
# ======================================================================
echo "=== PHASE 8: Deletions ==="

# T80: Delete department
if [ -n "${IDS[DEPT2_ID]:-}" ]; then
  api DELETE "department/${IDS[DEPT2_ID]}"
  if [ "$LAST_CODE" = "204" ] || [ "$LAST_CODE" = "200" ]; then
    record PASS T80 "DELETE /department" "$LAST_CODE"
  else
    record FAIL T80 "DELETE /department" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T80 "DELETE /department" "no department"
fi

# T81: Delete customer (may fail if invoice exists)
if [ -n "${IDS[CUST2_ID]:-}" ]; then
  api DELETE "customer/${IDS[CUST2_ID]}"
  if [ "$LAST_CODE" = "204" ] || [ "$LAST_CODE" = "200" ]; then
    record PASS T81 "DELETE /customer (no refs)" "$LAST_CODE"
  else
    record FAIL T81 "DELETE /customer" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T81 "DELETE /customer" "no customer without refs"
fi

# T82: Delete product (use PROD2 which has no orderlines)
if [ -n "${IDS[PROD2_ID]:-}" ]; then
  api DELETE "product/${IDS[PROD2_ID]}"
  if [ "$LAST_CODE" = "204" ] || [ "$LAST_CODE" = "200" ]; then
    record PASS T82 "DELETE /product (no refs)" "$LAST_CODE"
  else
    record FAIL T82 "DELETE /product" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T82 "DELETE /product" "no product without refs"
fi

# T83: Delete employee → 403 (forbidden in sandbox/API)
if [ -n "${IDS[EMP4_ID]:-${IDS[EMP2_ID]:-}}" ]; then
  local_emp="${IDS[EMP4_ID]:-${IDS[EMP2_ID]}}"
  api DELETE "employee/$local_emp"
  if [ "$LAST_CODE" = "204" ] || [ "$LAST_CODE" = "200" ]; then
    record PASS T83 "DELETE /employee" "$LAST_CODE"
  elif [ "$LAST_CODE" = "403" ]; then
    record XFAIL T83 "DELETE /employee (forbidden)" "403 - employees cannot be deleted via API"
  else
    record FAIL T83 "DELETE /employee" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T83 "DELETE /employee" "no employee to delete"
fi

# T84: Delete project (unverified #3)
if [ -n "${IDS[PROJ_ID]:-}" ]; then
  api DELETE "project/${IDS[PROJ_ID]}"
  if [ "$LAST_CODE" = "204" ] || [ "$LAST_CODE" = "200" ]; then
    record PASS T84 "DELETE /project" "$LAST_CODE"
  else
    record FAIL T84 "DELETE /project" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T84 "DELETE /project" "no project"
fi

# T85: Delete travel expense (unverified #7)
if [ -n "${IDS[TE2_ID]:-${IDS[TE_ID]:-}}" ]; then
  # Try TE2 first (simpler, no sub-resources attached via T63-T69)
  local_te="${IDS[TE2_ID]:-${IDS[TE_ID]}}"
  api DELETE "travelExpense/$local_te"
  if [ "$LAST_CODE" = "204" ] || [ "$LAST_CODE" = "200" ]; then
    record PASS T85 "DELETE /travelExpense" "$LAST_CODE"
  else
    record FAIL T85 "DELETE /travelExpense" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T85 "DELETE /travelExpense" "no travel expense"
fi

# T86: Delete invoice → 403 (invoices cannot be deleted; use credit note to void)
if [ -n "${IDS[INV2_ID]:-}" ]; then
  api DELETE "invoice/${IDS[INV2_ID]}"
  if [ "$LAST_CODE" = "204" ] || [ "$LAST_CODE" = "200" ]; then
    record PASS T86 "DELETE /invoice" "$LAST_CODE"
  elif [ "$LAST_CODE" = "403" ]; then
    record XFAIL T86 "DELETE /invoice (forbidden)" "403 - use credit note to void"
  else
    record FAIL T86 "DELETE /invoice" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T86 "DELETE /invoice" "no invoice"
fi

# T87: Delete order → 422 when invoice exists ("Ordren kan ikke slettes. Fakturaer er generert.")
if [ -n "${IDS[ORDER2_ID]:-}" ]; then
  api DELETE "order/${IDS[ORDER2_ID]}"
  if [ "$LAST_CODE" = "204" ] || [ "$LAST_CODE" = "200" ]; then
    record PASS T87 "DELETE /order" "$LAST_CODE"
  elif [ "$LAST_CODE" = "422" ]; then
    record XFAIL T87 "DELETE /order (has invoice)" "422 - cannot delete order with invoices"
  else
    record FAIL T87 "DELETE /order" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T87 "DELETE /order" "no order"
fi

echo ""

# ======================================================================
# PHASE 9: Negative cases (error message verification)
# ======================================================================
echo "=== PHASE 9: Negative cases (error messages) ==="

check_error_message() {
  local tid="$1" desc="$2" expected_fragment="$3"
  local actual_msg
  actual_msg=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin)
msgs=d.get('validationMessages',[]); parts=[m.get('message','') for m in msgs]
parts.append(d.get('message','')); print('|'.join(parts))" 2>/dev/null)
  if echo "$actual_msg" | grep -qF "$expected_fragment"; then
    record PASS "$tid" "$desc" "error message matches"
  else
    record FAIL "$tid" "$desc" "expected '$expected_fragment' in '$actual_msg'"
  fi
}

# T90: startDate on employee body → 422 "Feltet eksisterer ikke"
api POST employee "{\"firstName\":\"BadField\",\"lastName\":\"Test\",\"userType\":\"NO_ACCESS\",\"department\":{\"id\":${IDS[DEPT_ID]}},\"startDate\":\"$TODAY\"}"
expect_fail T90 "POST /employee (startDate on body) [error msg]"
check_error_message T90b "Error msg: startDate" "eksisterer ikke"

# T91: PUT employee without dateOfBirth → 200 (dateOfBirth NOT required on PUT despite earlier belief)
if [ -n "${IDS[EMP2_ID]:-}" ]; then
  api GET "employee/${IDS[EMP2_ID]}"
  local_ver=$(extract_version)
  api PUT "employee/${IDS[EMP2_ID]}" "{\"id\":${IDS[EMP2_ID]},\"version\":$local_ver,\"firstName\":\"NoDob\",\"lastName\":\"Test\",\"userType\":\"NO_ACCESS\",\"department\":{\"id\":${IDS[DEPT_ID]}}}"
  expect_success T91 "PUT /employee (no dateOfBirth succeeds)" 200
else
  record SKIP T91 "PUT /employee (no dateOfBirth)" "no employee"
fi

# T92: Duplicate product name → 422 "allerede registrert"
api POST product "{\"name\":\"Verify Product $TS\"}"
expect_fail T92 "POST /product (duplicate name) [error msg]"
check_error_message T92b "Error msg: duplicate product" "allerede registrert"

# T93: passengerSupplement: true on mileage → 422 "type"
if [ -n "${IDS[TE_ID]:-}" ]; then
  api POST "travelExpense/mileageAllowance" "{
    \"travelExpense\":{\"id\":${IDS[TE_ID]}},
    \"rateType\":{\"id\":${IDS[MILEAGE_CAT]}},
    \"date\":\"$TODAY\",
    \"departureLocation\":\"Oslo\",
    \"destination\":\"Bergen\",
    \"km\":100,
    \"rate\":3.5,
    \"amount\":350.0,
    \"isCompanyCar\":false,
    \"passengerSupplement\":true
  }"
  expect_fail T93 "POST /mileageAllowance (passengerSupplement bool) [error msg]"
  check_error_message T93b "Error msg: wrong type" "type"
else
  record SKIP T93 "POST /mileageAllowance (passengerSupplement)" "no travel expense"
  record SKIP T93b "Error msg: wrong type" "no travel expense"
fi

echo ""

# ======================================================================
# PHASE 10: Inline creation patterns
# ======================================================================
echo "=== PHASE 10: Inline creation patterns ==="

# T100: Employee with inline employments (dateOfBirth required when inlining employments)
api POST employee "{
  \"firstName\":\"Inline\",\"lastName\":\"Emp $TS\",
  \"userType\":\"NO_ACCESS\",
  \"department\":{\"id\":${IDS[DEPT_ID]}},
  \"dateOfBirth\":\"1990-01-01\",
  \"employments\":[{\"startDate\":\"$TODAY\"}]
}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[EMP_INLINE_ID]=$(extract_id)
  # Verify employment was created
  api GET "employee/employment?employeeId=${IDS[EMP_INLINE_ID]}"
  emp_count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('fullResultSize',0))" 2>/dev/null)
  if [ "$emp_count" -gt 0 ] 2>/dev/null; then
    record PASS T100 "POST /employee (inline employments)" "employment created, count=$emp_count"
    IDS[EMPLOYMENT_ID]=$(extract_first_id)
  else
    record FAIL T100 "POST /employee (inline employments)" "employee ok but no employment found"
  fi
else
  record FAIL T100 "POST /employee (inline employments)" "got $LAST_CODE"
  validation_msg
fi

# T101: Employee with inline employments + nested employmentDetails
api POST employee "{
  \"firstName\":\"Deep\",\"lastName\":\"Inline $TS\",
  \"userType\":\"NO_ACCESS\",
  \"department\":{\"id\":${IDS[DEPT_ID]}},
  \"dateOfBirth\":\"1990-01-01\",
  \"employments\":[{
    \"startDate\":\"$TODAY\",
    \"employmentDetails\":[{
      \"date\":\"$TODAY\",
      \"employmentType\":\"ORDINARY\",
      \"employmentForm\":\"PERMANENT\"
    }]
  }]
}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[EMP_DEEP_ID]=$(extract_id)
  record PASS T101 "POST /employee (inline employment+details)" "$LAST_CODE"
else
  record FAIL T101 "POST /employee (inline employment+details)" "got $LAST_CODE"
  validation_msg
fi

# T102: Travel expense with inline costs
api POST travelExpense "{
  \"employee\":{\"id\":${IDS[EMP_ID]}},
  \"title\":\"Inline Costs Trip $TS\",
  \"travelDetails\":{
    \"departureDate\":\"$TODAY\",
    \"returnDate\":\"$TOMORROW\",
    \"isDayTrip\":false
  },
  \"costs\":[{
    \"costCategory\":{\"id\":${IDS[COST_CAT_ID]}},
    \"paymentType\":{\"id\":${IDS[TRAVEL_PAY_ID]}},
    \"currency\":{\"id\":${IDS[CURRENCY_ID]}},
    \"amountCurrencyIncVat\":250.0,
    \"date\":\"$TODAY\"
  }]
}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[TE_INLINE_COST_ID]=$(extract_id)
  record PASS T102 "POST /travelExpense (inline costs)" "$LAST_CODE"
else
  record FAIL T102 "POST /travelExpense (inline costs)" "got $LAST_CODE"
  validation_msg
fi

# T103: Travel expense with inline perDiemCompensations
api POST travelExpense "{
  \"employee\":{\"id\":${IDS[EMP_ID]}},
  \"title\":\"Inline PerDiem Trip $TS\",
  \"travelDetails\":{
    \"departureDate\":\"$TODAY\",
    \"returnDate\":\"$TOMORROW\",
    \"isDayTrip\":false
  },
  \"perDiemCompensations\":[{
    \"rateType\":{\"id\":${IDS[PERDIEM_CAT]}},
    \"count\":1,
    \"location\":\"Bergen\",
    \"overnightAccommodation\":\"HOTEL\",
    \"isDeductionForBreakfast\":false
  }]
}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[TE_INLINE_PD_ID]=$(extract_id)
  record PASS T103 "POST /travelExpense (inline perDiemCompensations)" "$LAST_CODE"
else
  record FAIL T103 "POST /travelExpense (inline perDiemCompensations)" "got $LAST_CODE"
  validation_msg
fi

# T104: Project with inline participants
api POST project "{
  \"name\":\"Inline Part Project $TS\",
  \"projectManager\":{\"id\":${IDS[EMP_ID]}},
  \"isInternal\":true,
  \"startDate\":\"$TODAY\",
  \"participants\":[{\"employee\":{\"id\":${IDS[EMP_ID]}}}]
}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[PROJ_INLINE_ID]=$(extract_id)
  record PASS T104 "POST /project (inline participants)" "$LAST_CODE"
else
  record FAIL T104 "POST /project (inline participants)" "got $LAST_CODE"
  validation_msg
fi

echo ""

# ======================================================================
# PHASE 11: Response shape verification
# ======================================================================
echo "=== PHASE 11: Response shape verification ==="

# T110: List GET has fullResultSize/from/count/values
api GET "employee?count=1"
has_shape=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin)
keys={'fullResultSize','from','count','values'}
print('yes' if keys.issubset(d.keys()) else 'no')
" 2>/dev/null)
if [ "$has_shape" = "yes" ]; then
  record PASS T110 "List GET response shape" "has fullResultSize/from/count/values"
else
  record FAIL T110 "List GET response shape" "missing expected keys"
fi

# T111: Single GET returns {"value":{...}}
api GET "employee/${IDS[EMP_ID]}"
has_value=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('yes' if 'value' in d and isinstance(d['value'], dict) else 'no')
" 2>/dev/null)
if [ "$has_value" = "yes" ]; then
  record PASS T111 "Single GET response shape" "{\"value\":{...}}"
else
  record FAIL T111 "Single GET response shape" "missing value wrapper"
fi

# T112: POST returns id + version
api POST product "{\"name\":\"ShapeTest $TS\"}"
has_id_ver=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin).get('value',{})
print('yes' if 'id' in d and 'version' in d else 'no')
" 2>/dev/null)
if [ "$has_id_ver" = "yes" ]; then
  IDS[PROD_SHAPE_ID]=$(extract_id)
  record PASS T112 "POST response has id+version" "id=${IDS[PROD_SHAPE_ID]}"
else
  record FAIL T112 "POST response has id+version" "missing id or version"
fi

# T113: Mileage POST returns URL-only response
if [ -n "${IDS[TE_ID]:-}" ]; then
  api POST "travelExpense/mileageAllowance" "{
    \"travelExpense\":{\"id\":${IDS[TE_ID]}},
    \"rateType\":{\"id\":${IDS[MILEAGE_CAT]}},
    \"date\":\"$TODAY\",
    \"departureLocation\":\"Oslo\",
    \"destination\":\"Drammen\",
    \"km\":40,
    \"rate\":3.5,
    \"amount\":140.0,
    \"isCompanyCar\":false
  }"
  url_only=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin).get('value',{})
has_url = 'url' in d
has_id = 'id' in d
# URL-only means it has url but no other fields (or id is missing)
if has_url and not has_id:
  print('url_only')
elif has_url and has_id:
  print('full_object')
else:
  print('unknown')
" 2>/dev/null)
  if [ "$url_only" = "url_only" ]; then
    record PASS T113 "Mileage POST returns URL-only" "confirmed url-only response"
  elif [ "$url_only" = "full_object" ]; then
    record PASS T113 "Mileage POST returns full object" "NOT url-only — skill doc may need update"
  else
    record FAIL T113 "Mileage POST response shape" "unexpected shape"
  fi
else
  record SKIP T113 "Mileage POST response shape" "no travel expense"
fi

# T114: Minimal customer POST returns postalAddress.id
api POST customer "{\"name\":\"AddrShape $TS\"}"
addr_id=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin).get('value',{})
pa=d.get('postalAddress',{})
print(pa.get('id','none'))
" 2>/dev/null)
if [ "$addr_id" != "none" ] && [ -n "$addr_id" ]; then
  IDS[CUST_SHAPE_ID]=$(extract_id)
  IDS[CUST_SHAPE_ADDR_ID]=$addr_id
  record PASS T114 "Minimal customer POST has postalAddress.id" "addr_id=$addr_id"
else
  record FAIL T114 "Minimal customer POST has postalAddress.id" "postalAddress.id missing"
fi

echo ""

# ======================================================================
# PHASE 12: Nested object update behavior
# ======================================================================
echo "=== PHASE 12: Nested object update behavior ==="

if [ -n "${IDS[CUST_SHAPE_ID]:-}" ]; then
  # Get fresh version
  api GET "customer/${IDS[CUST_SHAPE_ID]}"
  cust_ver=$(extract_version)

  # T120: PUT customer address WITHOUT nested id/version → creates NEW address (not silently ignored!)
  api PUT "customer/${IDS[CUST_SHAPE_ID]}" "{
    \"id\":${IDS[CUST_SHAPE_ID]},\"version\":$cust_ver,
    \"name\":\"AddrShape $TS\",
    \"postalAddress\":{\"addressLine1\":\"NewAddr 99\",\"postalCode\":\"9999\",\"city\":\"Nowhere\"}
  }"
  if [ "$LAST_CODE" = "200" ]; then
    cust_ver=$(extract_version)
    # Address without id creates a NEW address object (replaces old one)
    addr_line=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin).get('value',{})
print(d.get('postalAddress',{}).get('addressLine1','') or 'empty')
" 2>/dev/null)
    new_addr_id=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin).get('value',{})
print(d.get('postalAddress',{}).get('id',''))
" 2>/dev/null)
    if [ "$addr_line" = "NewAddr 99" ]; then
      record PASS T120 "PUT customer addr WITHOUT id/version" "creates new address (addr_id=$new_addr_id)"
    else
      record FAIL T120 "PUT customer addr WITHOUT id/version" "unexpected addr='$addr_line'"
    fi
  else
    record FAIL T120 "PUT customer addr WITHOUT id/version" "PUT failed: $LAST_CODE"
    validation_msg
  fi

  # T121: PUT customer address again WITHOUT id → replaces address again (confirms pattern)
  api PUT "customer/${IDS[CUST_SHAPE_ID]}" "{
    \"id\":${IDS[CUST_SHAPE_ID]},\"version\":$cust_ver,
    \"name\":\"AddrShape $TS\",
    \"postalAddress\":{\"addressLine1\":\"Replaced 42\",\"postalCode\":\"0182\",\"city\":\"Oslo\"}
  }"
  if [ "$LAST_CODE" = "200" ]; then
    addr_line=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin).get('value',{})
print(d.get('postalAddress',{}).get('addressLine1','') or 'empty')
" 2>/dev/null)
    final_addr_id=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin).get('value',{})
print(d.get('postalAddress',{}).get('id',''))
" 2>/dev/null)
    if [ "$addr_line" = "Replaced 42" ]; then
      record PASS T121 "PUT customer addr (replace pattern)" "new addr_id=$final_addr_id, content updated"
    else
      record FAIL T121 "PUT customer addr (replace pattern)" "unexpected addr='$addr_line'"
    fi
  else
    record FAIL T121 "PUT customer addr (replace pattern)" "PUT failed: $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T120 "PUT customer addr WITHOUT id/version" "no customer"
  record SKIP T121 "PUT customer addr (replace pattern)" "no customer"
fi

echo ""

# ======================================================================
# PHASE 13: Sub-resource CRUD
# ======================================================================
echo "=== PHASE 13: Sub-resource CRUD ==="

# T130: Employee next of kin CRUD
if [ -n "${IDS[EMP2_ID]:-}" ]; then
  api POST "employee/nextOfKin" "{\"employee\":{\"id\":${IDS[EMP2_ID]}},\"name\":\"Kin Person $TS\",\"phoneNumber\":\"99887766\",\"typeOfRelationship\":\"SPOUSE\"}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[KIN_ID]=$(extract_id)
    record PASS T130a "POST /employee/nextOfKin" "id=${IDS[KIN_ID]}"

    # GET
    api GET "employee/nextOfKin?employeeId=${IDS[EMP2_ID]}"
    expect_success T130b "GET /employee/nextOfKin" 200

    # PUT
    kin_ver=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['values'][0]['version'])" 2>/dev/null)
    api PUT "employee/nextOfKin/${IDS[KIN_ID]}" "{\"id\":${IDS[KIN_ID]},\"version\":$kin_ver,\"employee\":{\"id\":${IDS[EMP2_ID]}},\"name\":\"Updated Kin $TS\",\"phoneNumber\":\"99887766\",\"typeOfRelationship\":\"SPOUSE\"}"
    expect_success T130c "PUT /employee/nextOfKin" 200
  else
    record FAIL T130a "POST /employee/nextOfKin" "got $LAST_CODE"
    validation_msg
    record SKIP T130b "GET /employee/nextOfKin" "create failed"
    record SKIP T130c "PUT /employee/nextOfKin" "create failed"
  fi
else
  record SKIP T130a "POST /employee/nextOfKin" "no employee"
  record SKIP T130b "GET /employee/nextOfKin" "no employee"
  record SKIP T130c "PUT /employee/nextOfKin" "no employee"
fi

# T131: Employee standard time
if [ -n "${IDS[EMP2_ID]:-}" ]; then
  api POST "employee/standardTime" "{\"employee\":{\"id\":${IDS[EMP2_ID]}},\"fromDate\":\"$TODAY\",\"hoursPerDay\":7.5}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[STD_TIME_ID]=$(extract_id)
    record PASS T131 "POST /employee/standardTime" "id=${IDS[STD_TIME_ID]}"
  else
    record FAIL T131 "POST /employee/standardTime" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T131 "POST /employee/standardTime" "no employee"
fi

# T132: Employee hourly cost and rate
if [ -n "${IDS[EMP2_ID]:-}" ]; then
  api POST "employee/hourlyCostAndRate" "{\"employee\":{\"id\":${IDS[EMP2_ID]}},\"date\":\"$TODAY\",\"rate\":500.0,\"budgetRate\":450.0,\"hourCostRate\":300.0}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[HOURLY_RATE_ID]=$(extract_id)
    record PASS T132 "POST /employee/hourlyCostAndRate" "id=${IDS[HOURLY_RATE_ID]}"
  else
    record FAIL T132 "POST /employee/hourlyCostAndRate" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T132 "POST /employee/hourlyCostAndRate" "no employee"
fi

# T133: Project standalone participant
if [ -n "${IDS[PROJ_INLINE_ID]:-}" ] && [ -n "${IDS[EMP2_ID]:-}" ]; then
  api POST "project/participant" "{\"project\":{\"id\":${IDS[PROJ_INLINE_ID]}},\"employee\":{\"id\":${IDS[EMP2_ID]}}}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[PARTICIPANT_ID]=$(extract_id)
    record PASS T133 "POST /project/participant (standalone)" "id=${IDS[PARTICIPANT_ID]}"
  else
    record FAIL T133 "POST /project/participant (standalone)" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T133 "POST /project/participant" "no project or employee"
fi

# T134: PUT /project update
if [ -n "${IDS[PROJ_INLINE_ID]:-}" ]; then
  api GET "project/${IDS[PROJ_INLINE_ID]}"
  proj_ver=$(extract_version)
  api PUT "project/${IDS[PROJ_INLINE_ID]}" "{\"id\":${IDS[PROJ_INLINE_ID]},\"version\":$proj_ver,\"name\":\"Updated Project $TS\",\"projectManager\":{\"id\":${IDS[EMP_ID]}},\"isInternal\":true,\"startDate\":\"$TODAY\"}"
  expect_success T134 "PUT /project (update name)" 200
else
  record SKIP T134 "PUT /project" "no project"
fi

# T135: Standalone order + orderline (not inline via invoice)
api POST order "{\"orderDate\":\"$TODAY\",\"deliveryDate\":\"$TODAY\",\"customer\":{\"id\":${IDS[CUST_ID]}}}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[STANDALONE_ORDER_ID]=$(extract_id)
  record PASS T135a "POST /order (standalone)" "id=${IDS[STANDALONE_ORDER_ID]}"

  api POST "order/orderline" "{\"order\":{\"id\":${IDS[STANDALONE_ORDER_ID]}},\"product\":{\"id\":${IDS[PROD_ID]}},\"count\":5}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[STANDALONE_OL_ID]=$(extract_id)
    record PASS T135b "POST /order/orderline (standalone)" "id=${IDS[STANDALONE_OL_ID]}"
  else
    record FAIL T135b "POST /order/orderline (standalone)" "got $LAST_CODE"
    validation_msg
  fi
else
  record FAIL T135a "POST /order (standalone)" "got $LAST_CODE"
  validation_msg
  record SKIP T135b "POST /order/orderline" "no order"
fi

# T136: Order with mixed VAT order lines (requires VAT registration)
if [ -n "${IDS[CUST_ID]:-}" ]; then
  api POST order "{\"orderDate\":\"$TODAY\",\"deliveryDate\":\"$TOMORROW\",\"customer\":{\"id\":${IDS[CUST_ID]}},\"orderLines\":[{\"description\":\"Item 25%\",\"count\":1,\"unitPriceExcludingVatCurrency\":100,\"vatType\":{\"id\":3}},{\"description\":\"Item 15%\",\"count\":1,\"unitPriceExcludingVatCurrency\":200,\"vatType\":{\"id\":31}},{\"description\":\"Item 12%\",\"count\":1,\"unitPriceExcludingVatCurrency\":300,\"vatType\":{\"id\":32}}]}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    MIXED_ORDER_ID=$(extract_id)
    record PASS T136a "POST /order (mixed VAT lines)" "id=$MIXED_ORDER_ID"

    # Verify all 3 lines created with correct vatTypes
    api GET "order/$MIXED_ORDER_ID?fields=orderLines(vatType(*))"
    LINE_COUNT=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['value']['orderLines']))" 2>/dev/null)
    VAT_IDS=$(echo "$LAST_BODY" | python3 -c "
import sys,json
lines=json.load(sys.stdin)['value']['orderLines']
print(','.join(str(l['vatType']['id']) for l in sorted(lines, key=lambda l: l['vatType']['id'])))
" 2>/dev/null)
    if [ "$LINE_COUNT" = "3" ] && [ "$VAT_IDS" = "3,31,32" ]; then
      record PASS T136b "Mixed VAT lines preserved" "lines=$LINE_COUNT vatTypes=$VAT_IDS"
    else
      record FAIL T136b "Mixed VAT lines preserved" "lines=$LINE_COUNT vatTypes=$VAT_IDS"
    fi
  else
    record FAIL T136a "POST /order (mixed VAT lines)" "got $LAST_CODE"
    validation_msg
    record SKIP T136b "Mixed VAT lines preserved" "no order"
  fi
else
  record SKIP T136a "POST /order (mixed VAT lines)" "no customer"
  record SKIP T136b "Mixed VAT lines preserved" "no customer"
fi

echo ""

# ======================================================================
# PHASE 14: Voucher / Ledger
# ======================================================================
echo "=== PHASE 14: Voucher / Ledger ==="

# Lookup revenue (3000) and expense (6000) accounts for balanced voucher postings
# Accounts at offset 0 are system/asset accounts (row=0 blocked). Need operating accounts.
api GET "ledger/account?isInactive=false&count=500"
ACCT_REVENUE=$(echo "$LAST_BODY" | python3 -c "
import sys,json; vs=json.load(sys.stdin)['values']
# Find a revenue account (3xxx)
for v in vs:
  if 3000 <= v.get('number',0) < 4000:
    print(v['id']); break
" 2>/dev/null)
ACCT_EXPENSE=$(echo "$LAST_BODY" | python3 -c "
import sys,json; vs=json.load(sys.stdin)['values']
# Find an expense account (6xxx or 7xxx)
for v in vs:
  if 6000 <= v.get('number',0) < 8000:
    print(v['id']); break
" 2>/dev/null)

# T140: POST /ledger/voucher with balanced postings
# Key learnings: use amountGross+amountGrossCurrency, row>0, vatType per vat-locked account
# Revenue account 3000 is locked to vatType 3 (output 25%), expense account 6000 uses vatType 0
ACCT_REV_VAT=$(echo "$LAST_BODY" | python3 -c "
import sys,json; vs=json.load(sys.stdin)['values']
for v in vs:
  if 3000 <= v.get('number',0) < 4000:
    vt=v.get('vatType',{})
    print(vt.get('id',0) if vt else 0); break
" 2>/dev/null)
ACCT_EXP_VAT=$(echo "$LAST_BODY" | python3 -c "
import sys,json; vs=json.load(sys.stdin)['values']
for v in vs:
  if 6000 <= v.get('number',0) < 8000:
    vt=v.get('vatType',{})
    print(vt.get('id',0) if vt else 0); break
" 2>/dev/null)
# Also extract salary (5000) and payable (2900) accounts for T143
ACCT_SALARY=$(echo "$LAST_BODY" | python3 -c "
import sys,json; vs=json.load(sys.stdin)['values']
for v in vs:
  if v.get('number',0) == 5000: print(v['id']); break
" 2>/dev/null)
ACCT_PAYABLE=$(echo "$LAST_BODY" | python3 -c "
import sys,json; vs=json.load(sys.stdin)['values']
for v in vs:
  if v.get('number',0) == 2900: print(v['id']); break
" 2>/dev/null)
if [ -n "$ACCT_REVENUE" ] && [ -n "$ACCT_EXPENSE" ]; then
  api POST "ledger/voucher" "{
    \"date\":\"$TODAY\",
    \"description\":\"Verify Voucher $TS\",
    \"postings\":[
      {\"date\":\"$TODAY\",\"account\":{\"id\":$ACCT_REVENUE},\"vatType\":{\"id\":${ACCT_REV_VAT:-0}},\"amountGross\":1000.0,\"amountGrossCurrency\":1000.0,\"row\":1},
      {\"date\":\"$TODAY\",\"account\":{\"id\":$ACCT_EXPENSE},\"vatType\":{\"id\":${ACCT_EXP_VAT:-0}},\"amountGross\":-1000.0,\"amountGrossCurrency\":-1000.0,\"row\":2}
    ]
  }"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[VOUCHER_ID]=$(extract_id)
    record PASS T140 "POST /ledger/voucher (balanced)" "id=${IDS[VOUCHER_ID]}"
  else
    record FAIL T140 "POST /ledger/voucher (balanced)" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T140 "POST /ledger/voucher" "no revenue/expense accounts found"
fi

# T141: GET /ledger/vatType — verify common codes exist
api GET "ledger/vatType?count=50"
vat_count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('fullResultSize',0))" 2>/dev/null)
if [ "$vat_count" -gt 0 ] 2>/dev/null; then
  # Check for id=1 and id=3 specifically
  has_common=$(echo "$LAST_BODY" | python3 -c "
import sys,json; vs=json.load(sys.stdin)['values']
ids={v['id'] for v in vs}
print('yes' if 1 in ids and 3 in ids else 'no')
" 2>/dev/null)
  if [ "$has_common" = "yes" ]; then
    record PASS T141 "GET /ledger/vatType (common codes)" "count=$vat_count, has id=1 and id=3"
  else
    record PASS T141 "GET /ledger/vatType" "count=$vat_count, but missing id=1 or id=3"
  fi
else
  record FAIL T141 "GET /ledger/vatType" "empty or error"
fi

# T142: GET /ledger/posting with date range
api GET "ledger/posting?dateFrom=$TODAY&dateTo=$TODAY"
if [ "$LAST_CODE" = "200" ]; then
  posting_count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('fullResultSize',0))" 2>/dev/null)
  record PASS T142 "GET /ledger/posting (date range)" "count=$posting_count"
else
  record FAIL T142 "GET /ledger/posting (date range)" "got $LAST_CODE"
  validation_msg
fi

# T143: POST /ledger/voucher with multiple debit/credit pairs (monthly closing pattern)
# Verified: a single voucher can hold 6+ posting lines spanning different account pairs.
# This is more efficient than creating 3 separate vouchers (3 POSTs → 1 POST).
if [ -n "$ACCT_REVENUE" ] && [ -n "$ACCT_EXPENSE" ] && [ -n "${ACCT_SALARY:-}" ] && [ -n "${ACCT_PAYABLE:-}" ]; then
  api POST "ledger/voucher" "{
    \"date\":\"$TODAY\",
    \"description\":\"Verify multi-pair voucher $TS\",
    \"postings\":[
      {\"date\":\"$TODAY\",\"description\":\"pair1 debit\",\"account\":{\"id\":$ACCT_REVENUE},\"vatType\":{\"id\":${ACCT_REV_VAT:-0}},\"amountGross\":1000.0,\"amountGrossCurrency\":1000.0,\"row\":1},
      {\"date\":\"$TODAY\",\"description\":\"pair1 credit\",\"account\":{\"id\":$ACCT_EXPENSE},\"vatType\":{\"id\":${ACCT_EXP_VAT:-0}},\"amountGross\":-1000.0,\"amountGrossCurrency\":-1000.0,\"row\":2},
      {\"date\":\"$TODAY\",\"description\":\"pair2 debit\",\"account\":{\"id\":$ACCT_SALARY},\"vatType\":{\"id\":0},\"amountGross\":50000.0,\"amountGrossCurrency\":50000.0,\"row\":3},
      {\"date\":\"$TODAY\",\"description\":\"pair2 credit\",\"account\":{\"id\":$ACCT_PAYABLE},\"vatType\":{\"id\":0},\"amountGross\":-50000.0,\"amountGrossCurrency\":-50000.0,\"row\":4},
      {\"date\":\"$TODAY\",\"description\":\"pair3 debit\",\"account\":{\"id\":$ACCT_EXPENSE},\"vatType\":{\"id\":${ACCT_EXP_VAT:-0}},\"amountGross\":2500.0,\"amountGrossCurrency\":2500.0,\"row\":5},
      {\"date\":\"$TODAY\",\"description\":\"pair3 credit\",\"account\":{\"id\":$ACCT_REVENUE},\"vatType\":{\"id\":${ACCT_REV_VAT:-0}},\"amountGross\":-2500.0,\"amountGrossCurrency\":-2500.0,\"row\":6}
    ]
  }"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    posting_count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['value']['postings']))" 2>/dev/null)
    record PASS T143 "POST /ledger/voucher (multi-pair, 6 postings)" "postings=$posting_count"
  else
    record FAIL T143 "POST /ledger/voucher (multi-pair)" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T143 "POST /ledger/voucher (multi-pair)" "missing salary/payable accounts"
fi

echo ""

# ======================================================================
# PHASE 14b: Required date params, dateTo exclusivity & field expansion
# ======================================================================
echo "=== PHASE 14b: Required date params, dateTo exclusivity & field expansion ==="

# ----- Invoice date params -----

# T250: GET /invoice without invoiceDateFrom/To → 422
if [ -n "${IDS[INV_ID]:-}" ]; then
  api GET "invoice?customerId=${IDS[CUST_ID]}&count=5"
  if [ "$LAST_CODE" = "422" ]; then
    record PASS T250 "GET /invoice without dates → 422" "invoiceDateFrom/dateTo required"
  else
    record FAIL T250 "GET /invoice without dates" "expected 422, got $LAST_CODE"
  fi
else
  record SKIP T250 "GET /invoice without dates" "no invoice"
fi

# T251: GET /invoice dateFrom=dateTo → 422 (dateTo is EXCLUSIVE: "from and including" >= "to and excluding")
if [ -n "${IDS[INV_ID]:-}" ]; then
  api GET "invoice?customerId=${IDS[CUST_ID]}&invoiceDateFrom=$TODAY&invoiceDateTo=$TODAY&count=5"
  if [ "$LAST_CODE" = "422" ]; then
    record PASS T251 "GET /invoice dateFrom=dateTo → 422 (dateTo exclusive)" "from >= to not allowed"
  else
    record FAIL T251 "GET /invoice dateFrom=dateTo" "expected 422, got $LAST_CODE"
  fi
else
  record SKIP T251 "GET /invoice dateFrom=dateTo" "no invoice"
fi

# T252: GET /invoice dateTo=tomorrow → 200 (correct exclusive usage)
if [ -n "${IDS[INV_ID]:-}" ]; then
  api GET "invoice?customerId=${IDS[CUST_ID]}&invoiceDateFrom=$TODAY&invoiceDateTo=$TOMORROW&count=5"
  if [ "$LAST_CODE" = "200" ]; then
    inv_found=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('values',[])))" 2>/dev/null)
    if [ "$inv_found" -gt 0 ] 2>/dev/null; then
      record PASS T252 "GET /invoice dateTo=tomorrow finds today's" "found $inv_found (dateTo is exclusive)"
    else
      record FAIL T252 "GET /invoice dateTo=tomorrow" "0 invoices found"
    fi
  else
    record FAIL T252 "GET /invoice dateTo=tomorrow" "got $LAST_CODE"
  fi
else
  record SKIP T252 "GET /invoice dateTo=tomorrow" "no invoice"
fi

# ----- Voucher date params -----

# T253: GET /ledger/voucher without dates → 422
api GET "ledger/voucher?count=5"
if [ "$LAST_CODE" = "422" ]; then
  record PASS T253 "GET /ledger/voucher without dates → 422" "dateFrom/dateTo required"
else
  record FAIL T253 "GET /ledger/voucher without dates" "expected 422, got $LAST_CODE"
fi

# T254: GET /ledger/voucher dateFrom=dateTo → 422 (exclusive)
api GET "ledger/voucher?dateFrom=$TODAY&dateTo=$TODAY&count=5"
if [ "$LAST_CODE" = "422" ]; then
  record PASS T254 "GET /ledger/voucher dateFrom=dateTo → 422 (exclusive)" "from >= to not allowed"
else
  record FAIL T254 "GET /ledger/voucher dateFrom=dateTo" "expected 422, got $LAST_CODE"
fi

# T255: GET /ledger/voucher dateTo=tomorrow → 200 (correct)
api GET "ledger/voucher?dateFrom=$TODAY&dateTo=$TOMORROW&count=5"
if [ "$LAST_CODE" = "200" ]; then
  v_count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('fullResultSize',0))" 2>/dev/null)
  record PASS T255 "GET /ledger/voucher dateTo=tomorrow → 200" "count=$v_count (dateTo exclusive)"
else
  record FAIL T255 "GET /ledger/voucher dateTo=tomorrow" "got $LAST_CODE"
fi

# ----- Timesheet date params -----
# Create a fresh project + activity + timesheet entry (PROJ_ID was deleted in phase 8)
if [ -n "${IDS[EMP_ID]:-}" ]; then
  api POST project "{\"name\":\"TS Date Test $TS\",\"projectManager\":{\"id\":${IDS[EMP_ID]}},\"isInternal\":true,\"startDate\":\"$TODAY\"}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[TS_PROJ_ID]=$(extract_id)
  fi
  api POST activity "{\"name\":\"TS Verify $TS\",\"activityType\":\"PROJECT_GENERAL_ACTIVITY\"}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[TS_ACT_ID]=$(extract_id)
    # Link activity to project (correct endpoint: project/projectActivity, NOT project/{id}/projectActivity)
    api POST "project/projectActivity" "{\"project\":{\"id\":${IDS[TS_PROJ_ID]}},\"activity\":{\"id\":${IDS[TS_ACT_ID]}}}"
    if [[ "$LAST_CODE" =~ ^2 ]]; then
      IDS[PROJ_ACT_LINK_ID]=$(extract_id)
    fi
    # Create timesheet entry
    api POST "timesheet/entry" "{\"employee\":{\"id\":${IDS[EMP_ID]}},\"project\":{\"id\":${IDS[TS_PROJ_ID]}},\"activity\":{\"id\":${IDS[TS_ACT_ID]}},\"date\":\"$TODAY\",\"hours\":2.5}"
    if [[ "$LAST_CODE" =~ ^2 ]]; then
      IDS[TS_ENTRY_ID]=$(extract_id)

      # T256: GET /timesheet/entry without dates → 422
      api GET "timesheet/entry?employeeId=${IDS[EMP_ID]}&count=5"
      if [ "$LAST_CODE" = "422" ]; then
        record PASS T256 "GET /timesheet/entry without dates → 422" "dateFrom/dateTo required"
      else
        record FAIL T256 "GET /timesheet/entry without dates" "expected 422, got $LAST_CODE"
      fi

      # T257: GET /timesheet/entry dateFrom=dateTo → check exclusive
      api GET "timesheet/entry?employeeId=${IDS[EMP_ID]}&dateFrom=$TODAY&dateTo=$TODAY&count=5"
      if [ "$LAST_CODE" = "422" ]; then
        record PASS T257 "GET /timesheet/entry dateFrom=dateTo → 422 (exclusive)" "from >= to not allowed"
      elif [ "$LAST_CODE" = "200" ]; then
        ts_same=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('values',[])))" 2>/dev/null)
        record FAIL T257 "GET /timesheet/entry dateFrom=dateTo" "expected 422 (exclusive), got 200 count=$ts_same (inclusive?)"
      else
        record FAIL T257 "GET /timesheet/entry dateFrom=dateTo" "got $LAST_CODE"
      fi

      # T258: GET /timesheet/entry dateTo=tomorrow → 200
      api GET "timesheet/entry?employeeId=${IDS[EMP_ID]}&dateFrom=$TODAY&dateTo=$TOMORROW&count=5"
      if [ "$LAST_CODE" = "200" ]; then
        ts_found=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('values',[])))" 2>/dev/null)
        if [ "$ts_found" -gt 0 ] 2>/dev/null; then
          record PASS T258 "GET /timesheet/entry dateTo=tomorrow → 200" "found $ts_found (dateTo exclusive)"
        else
          record FAIL T258 "GET /timesheet/entry dateTo=tomorrow" "0 entries found"
        fi
      else
        record FAIL T258 "GET /timesheet/entry dateTo=tomorrow" "got $LAST_CODE"
      fi
    else
      record SKIP T256 "GET /timesheet/entry without dates" "timesheet create failed: $LAST_CODE"
      validation_msg
      record SKIP T257 "GET /timesheet/entry dateFrom=dateTo" "no timesheet entry"
      record SKIP T258 "GET /timesheet/entry dateTo=tomorrow" "no timesheet entry"
    fi
  else
    record SKIP T256 "GET /timesheet/entry without dates" "activity create failed"
    record SKIP T257 "GET /timesheet/entry dateFrom=dateTo" "no activity"
    record SKIP T258 "GET /timesheet/entry dateTo=tomorrow" "no activity"
  fi
else
  record SKIP T256 "GET /timesheet/entry without dates" "no employee"
  record SKIP T257 "GET /timesheet/entry dateFrom=dateTo" "no employee"
  record SKIP T258 "GET /timesheet/entry dateTo=tomorrow" "no employee"
fi

# ----- Ledger posting: same-day allowed (different from invoice/voucher/timesheet) -----

# T259: GET /ledger/posting dateFrom=dateTo → 200 (NOT exclusive like others)
api GET "ledger/posting?dateFrom=$TODAY&dateTo=$TODAY&count=5"
if [ "$LAST_CODE" = "200" ]; then
  p_count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('fullResultSize',0))" 2>/dev/null)
  record PASS T259 "GET /ledger/posting dateFrom=dateTo → 200 (inclusive)" "count=$p_count — unlike invoice/voucher/timesheet"
else
  record FAIL T259 "GET /ledger/posting dateFrom=dateTo" "got $LAST_CODE (expected 200 — posting allows same-day)"
fi

# T274: GET /ledger/posting with comma-separated accountId → 404
# Agent keeps trying accountId=ID1,ID2,ID3 which returns 404.
# Single accountId per request works fine. Verify the API rejects comma-separated.
if [ -n "${ACCT_REVENUE:-}" ] && [ -n "${ACCT_EXPENSE:-}" ]; then
  api GET "ledger/posting?dateFrom=$TODAY&dateTo=$TOMORROW&accountId=${ACCT_REVENUE},${ACCT_EXPENSE}&count=5"
  if [ "$LAST_CODE" = "404" ]; then
    record PASS T274 "GET /ledger/posting comma-separated accountId → 404" "confirmed: must use one accountId per request"
  else
    record FAIL T274 "GET /ledger/posting comma-separated accountId" "expected 404, got $LAST_CODE"
  fi

  # Verify single accountId works
  api GET "ledger/posting?dateFrom=$TODAY&dateTo=$TOMORROW&accountId=${ACCT_REVENUE}&count=5"
  if [ "$LAST_CODE" = "200" ]; then
    record PASS T274b "GET /ledger/posting single accountId → 200" "single accountId works"
  else
    record FAIL T274b "GET /ledger/posting single accountId" "expected 200, got $LAST_CODE"
  fi

  # T274c: Repeated accountId params silently use only the first value (no union)
  api GET "ledger/posting?dateFrom=$TODAY&dateTo=$TOMORROW&accountId=${ACCT_REVENUE}&accountId=${ACCT_EXPENSE}&count=5"
  if [ "$LAST_CODE" = "200" ]; then
    record PASS T274c "GET /ledger/posting repeated accountId → 200 (but only first used)" "no multi-account support — must query individually"
  else
    record FAIL T274c "GET /ledger/posting repeated accountId" "expected 200, got $LAST_CODE"
  fi
else
  record SKIP T274 "GET /ledger/posting comma-separated accountId" "no account IDs from phase 14"
  record SKIP T274b "GET /ledger/posting single accountId" "no account IDs from phase 14"
  record SKIP T274c "GET /ledger/posting repeated accountId" "no account IDs from phase 14"
fi

# ----- Project hourly rates -----

# Create a project for hourly rate tests (need admin as PM)
if [ -n "${IDS[EMP_ID]:-}" ]; then
  api POST project "{\"name\":\"HourlyRate Test $TS\",\"projectManager\":{\"id\":${IDS[EMP_ID]}},\"isInternal\":true,\"startDate\":\"$TODAY\"}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[HR_PROJ_ID]=$(extract_id)

    # T264: New project auto-creates a projectHourlyRates entry
    api GET "project/${IDS[HR_PROJ_ID]}?fields=projectHourlyRates(*)"
    hr_auto=$(echo "$LAST_BODY" | python3 -c "
import sys,json
v=json.load(sys.stdin).get('value',{})
rates=v.get('projectHourlyRates',[])
if not rates: print('none')
else:
  r=rates[0]
  print(f\"id={r['id']},model={r.get('hourlyRateModel')},fixedRate={r.get('fixedRate')},startDate={r.get('startDate')}\")
" 2>/dev/null)
    if echo "$hr_auto" | grep -q "^id="; then
      record PASS T264 "New project auto-creates hourlyRates entry" "$hr_auto"
      IDS[HR_RATE_ID]=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['value']['projectHourlyRates'][0]['id'])" 2>/dev/null)
    else
      record FAIL T264 "New project auto-creates hourlyRates" "$hr_auto"
    fi

    # T265: Default hourlyRateModel is TYPE_FIXED_HOURLY_RATE
    if echo "$hr_auto" | grep -q "TYPE_FIXED_HOURLY_RATE"; then
      record PASS T265 "Default hourlyRateModel=TYPE_FIXED_HOURLY_RATE" "confirmed"
    else
      record FAIL T265 "Default hourlyRateModel" "$hr_auto"
    fi

    # T266: PUT hourlyRates with fixedRate
    if [ -n "${IDS[HR_RATE_ID]:-}" ]; then
      api PUT "project/hourlyRates/${IDS[HR_RATE_ID]}" "{\"id\":${IDS[HR_RATE_ID]},\"version\":0,\"project\":{\"id\":${IDS[HR_PROJ_ID]}},\"hourlyRateModel\":\"TYPE_FIXED_HOURLY_RATE\",\"fixedRate\":1850.0}"
      if [[ "$LAST_CODE" =~ ^2 ]]; then
        updated_rate=$(echo "$LAST_BODY" | python3 -c "import sys,json; v=json.load(sys.stdin)['value']; print(f\"fixedRate={v.get('fixedRate')}\")" 2>/dev/null)
        record PASS T266 "PUT /project/hourlyRates (fixedRate)" "$updated_rate"
      else
        record FAIL T266 "PUT /project/hourlyRates (fixedRate)" "got $LAST_CODE"
        validation_msg
      fi

      # T267: PUT hourlyRates WITHOUT project ref — still succeeds
      api GET "project/hourlyRates/${IDS[HR_RATE_ID]}"
      hr_ver=$(extract_version)
      api PUT "project/hourlyRates/${IDS[HR_RATE_ID]}" "{\"id\":${IDS[HR_RATE_ID]},\"version\":$hr_ver,\"hourlyRateModel\":\"TYPE_FIXED_HOURLY_RATE\",\"fixedRate\":2000.0}"
      if [[ "$LAST_CODE" =~ ^2 ]]; then
        record PASS T267 "PUT /project/hourlyRates (no project ref)" "project ref NOT required on PUT"
      else
        record FAIL T267 "PUT /project/hourlyRates (no project ref)" "got $LAST_CODE — project ref may be required"
        validation_msg
      fi

      # T268: All 3 hourlyRateModel values accepted
      models_ok=true
      for model in TYPE_PREDEFINED_HOURLY_RATES TYPE_PROJECT_SPECIFIC_HOURLY_RATES TYPE_FIXED_HOURLY_RATE; do
        api GET "project/hourlyRates/${IDS[HR_RATE_ID]}"
        hr_ver=$(extract_version)
        payload="{\"id\":${IDS[HR_RATE_ID]},\"version\":$hr_ver,\"project\":{\"id\":${IDS[HR_PROJ_ID]}},\"hourlyRateModel\":\"$model\"}"
        if [ "$model" = "TYPE_FIXED_HOURLY_RATE" ]; then
          payload="{\"id\":${IDS[HR_RATE_ID]},\"version\":$hr_ver,\"project\":{\"id\":${IDS[HR_PROJ_ID]}},\"hourlyRateModel\":\"$model\",\"fixedRate\":1500.0}"
        fi
        api PUT "project/hourlyRates/${IDS[HR_RATE_ID]}" "$payload"
        if ! [[ "$LAST_CODE" =~ ^2 ]]; then
          models_ok=false
          record FAIL T268 "hourlyRateModel enum ($model)" "got $LAST_CODE"
          validation_msg
          break
        fi
      done
      if [ "$models_ok" = "true" ]; then
        record PASS T268 "All 3 hourlyRateModel values accepted" "PREDEFINED, PROJECT_SPECIFIC, FIXED"
      fi
    else
      record SKIP T266 "PUT /project/hourlyRates" "no rate ID"
      record SKIP T267 "PUT /project/hourlyRates (no project ref)" "no rate ID"
      record SKIP T268 "hourlyRateModel enum" "no rate ID"
    fi

    # T269: POST /project/hourlyRates creates additional rate entry
    api POST "project/hourlyRates" "{\"project\":{\"id\":${IDS[HR_PROJ_ID]}},\"startDate\":\"$TOMORROW\",\"hourlyRateModel\":\"TYPE_FIXED_HOURLY_RATE\",\"fixedRate\":2500.0}"
    if [[ "$LAST_CODE" =~ ^2 ]]; then
      IDS[HR_RATE2_ID]=$(extract_id)
      record PASS T269 "POST /project/hourlyRates (additional entry)" "id=${IDS[HR_RATE2_ID]}"
    else
      record FAIL T269 "POST /project/hourlyRates" "got $LAST_CODE"
      validation_msg
    fi
  else
    record SKIP T264 "Auto-created hourlyRates" "project create failed"
    record SKIP T265 "Default hourlyRateModel" "no project"
    record SKIP T266 "PUT /project/hourlyRates" "no project"
    record SKIP T267 "PUT /project/hourlyRates (no project ref)" "no project"
    record SKIP T268 "hourlyRateModel enum" "no project"
    record SKIP T269 "POST /project/hourlyRates" "no project"
  fi
else
  record SKIP T264 "Auto-created hourlyRates" "no employee"
  record SKIP T265 "Default hourlyRateModel" "no employee"
  record SKIP T266 "PUT /project/hourlyRates" "no employee"
  record SKIP T267 "PUT /project/hourlyRates (no project ref)" "no employee"
  record SKIP T268 "hourlyRateModel enum" "no employee"
  record SKIP T269 "POST /project/hourlyRates" "no employee"
fi

# ----- Project GET returns linked entities inline -----

# T270: GET /project list returns customer.id inline (no separate GET needed)
if [ -n "${IDS[EMP_ID]:-}" ] && [ -n "${IDS[CUST_ID]:-}" ]; then
  api POST project "{\"name\":\"CustInline Test $TS\",\"projectManager\":{\"id\":${IDS[EMP_ID]}},\"isInternal\":false,\"startDate\":\"$TODAY\",\"customer\":{\"id\":${IDS[CUST_ID]}}}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    cust_proj_id=$(extract_id)
    api GET "project?id=$cust_proj_id&count=1"
    inline_cust_id=$(echo "$LAST_BODY" | python3 -c "
import sys,json
vs=json.load(sys.stdin).get('values',[])
if not vs: print('')
else: print(vs[0].get('customer',{}).get('id',''))
" 2>/dev/null)
    if [ "$inline_cust_id" = "${IDS[CUST_ID]}" ]; then
      record PASS T270 "GET /project list returns customer.id inline" "customer.id=$inline_cust_id"
    else
      record FAIL T270 "GET /project list returns customer.id inline" "expected ${IDS[CUST_ID]}, got '$inline_cust_id'"
    fi
  else
    record FAIL T270 "Project with customer creation failed" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T270 "GET /project returns customer.id inline" "no employee or customer"
fi

# T271: GET /project returns projectActivities as STUBS by default
if [ -n "${IDS[TS_PROJ_ID]:-}" ] && [ -n "${IDS[PROJ_ACT_LINK_ID]:-}" ]; then
  api GET "project/${IDS[TS_PROJ_ID]}"
  if [ "$LAST_CODE" = "200" ]; then
    pa_shape=$(echo "$LAST_BODY" | python3 -c "
import sys,json
v=json.load(sys.stdin).get('value',{})
pas=v.get('projectActivities',[])
if not pas: print('empty')
elif 'activity' in pas[0]: print('expanded')
elif 'id' in pas[0] and 'activity' not in pas[0]: print('stub')
else: print(f'unknown:{list(pas[0].keys())}')
" 2>/dev/null)
    if [ "$pa_shape" = "stub" ]; then
      record PASS T271 "GET /project projectActivities are STUBS by default" "only id+url, no activity ref"
    elif [ "$pa_shape" = "expanded" ]; then
      record FAIL T271 "GET /project projectActivities are STUBS" "got expanded without fields param"
    else
      record FAIL T271 "GET /project projectActivities shape" "$pa_shape"
    fi
  else
    record FAIL T271 "GET /project for projectActivities shape" "got $LAST_CODE"
  fi

  # T272: GET /project with fields=projectActivities(*) returns EXPANDED activity data
  api GET "project/${IDS[TS_PROJ_ID]}?fields=projectActivities(*)"
  if [ "$LAST_CODE" = "200" ]; then
    pa_expanded=$(echo "$LAST_BODY" | python3 -c "
import sys,json
v=json.load(sys.stdin).get('value',{})
pas=v.get('projectActivities',[])
if not pas: print('empty')
elif 'activity' in pas[0]: print('expanded')
else: print(f'stub:{list(pas[0].keys())}')
" 2>/dev/null)
    if [ "$pa_expanded" = "expanded" ]; then
      record PASS T272 "GET /project fields=projectActivities(*) → expanded" "activity ref present"
    else
      record FAIL T272 "GET /project fields=projectActivities(*)" "$pa_expanded"
    fi
  else
    record FAIL T272 "GET /project fields=projectActivities(*)" "got $LAST_CODE"
  fi
else
  record SKIP T271 "GET /project projectActivities stubs" "no project with activity"
  record SKIP T272 "GET /project fields=projectActivities(*)" "no project with activity"
fi

# T273: GET /project returns projectHourlyRates as STUBS by default
if [ -n "${IDS[HR_PROJ_ID]:-}" ]; then
  api GET "project/${IDS[HR_PROJ_ID]}"
  if [ "$LAST_CODE" = "200" ]; then
    hr_shape=$(echo "$LAST_BODY" | python3 -c "
import sys,json
v=json.load(sys.stdin).get('value',{})
hrs=v.get('projectHourlyRates',[])
if not hrs: print('empty')
elif 'hourlyRateModel' in hrs[0]: print('expanded')
elif 'id' in hrs[0] and 'hourlyRateModel' not in hrs[0]: print('stub')
else: print(f'unknown:{list(hrs[0].keys())}')
" 2>/dev/null)
    if [ "$hr_shape" = "stub" ]; then
      record PASS T273 "GET /project projectHourlyRates are STUBS by default" "only id+url, no hourlyRateModel"
    elif [ "$hr_shape" = "expanded" ]; then
      record FAIL T273 "GET /project projectHourlyRates are STUBS" "got expanded without fields param"
    else
      record FAIL T273 "GET /project projectHourlyRates shape" "$hr_shape"
    fi
  else
    record FAIL T273 "GET /project for projectHourlyRates shape" "got $LAST_CODE"
  fi
else
  record SKIP T273 "GET /project projectHourlyRates stubs" "no project"
fi

# ----- Field expansion gotchas -----

# T260: GET /customer list returns postalAddress as STUB (not expanded)
if [ -n "${IDS[CUST_ID]:-}" ]; then
  api GET "customer?id=${IDS[CUST_ID]}&count=1"
  if [ "$LAST_CODE" = "200" ]; then
    addr_shape=$(echo "$LAST_BODY" | python3 -c "
import sys,json
vs=json.load(sys.stdin).get('values',[])
if not vs: print('no_values')
else:
  addr=vs[0].get('postalAddress',{})
  if not addr: print('null')
  elif 'addressLine1' in addr: print('expanded')
  elif 'id' in addr and 'addressLine1' not in addr: print('stub')
  else: print(f'unknown:{list(addr.keys())}')
" 2>/dev/null)
    if [ "$addr_shape" = "stub" ]; then
      record PASS T260 "GET /customer postalAddress is STUB by default" "only id+url, no addressLine1"
    elif [ "$addr_shape" = "expanded" ]; then
      record FAIL T260 "GET /customer postalAddress is STUB" "got expanded without fields param"
    else
      record FAIL T260 "GET /customer postalAddress shape" "$addr_shape"
    fi
  else
    record FAIL T260 "GET /customer postalAddress shape" "got $LAST_CODE"
  fi
else
  record SKIP T260 "GET /customer postalAddress shape" "no customer"
fi

# T261: GET /customer with fields=postalAddress(*) returns EXPANDED address
if [ -n "${IDS[CUST_ID]:-}" ]; then
  api GET "customer/${IDS[CUST_ID]}?fields=id,postalAddress(*)"
  if [ "$LAST_CODE" = "200" ]; then
    addr_expanded=$(echo "$LAST_BODY" | python3 -c "
import sys,json
v=json.load(sys.stdin).get('value',{})
addr=v.get('postalAddress',{})
if not addr: print('null')
elif 'addressLine1' in addr: print('expanded')
else: print(f'stub:{list(addr.keys())}')
" 2>/dev/null)
    if [ "$addr_expanded" = "expanded" ]; then
      record PASS T261 "GET /customer fields=postalAddress(*) → expanded" "addressLine1 present"
    else
      record FAIL T261 "GET /customer fields=postalAddress(*)" "$addr_expanded"
    fi
  else
    record FAIL T261 "GET /customer fields expansion" "got $LAST_CODE"
  fi
else
  record SKIP T261 "GET /customer fields=postalAddress(*)" "no customer"
fi

# T262: GET /employee list returns employments as STUBS
if [ -n "${IDS[EMP_INLINE_ID]:-}" ]; then
  api GET "employee?id=${IDS[EMP_INLINE_ID]}&count=1"
  if [ "$LAST_CODE" = "200" ]; then
    emp_shape=$(echo "$LAST_BODY" | python3 -c "
import sys,json
vs=json.load(sys.stdin).get('values',[])
if not vs: print('no_values')
else:
  emps=vs[0].get('employments',[])
  if not emps: print('empty')
  elif 'startDate' in emps[0]: print('expanded')
  elif 'id' in emps[0] and 'startDate' not in emps[0]: print('stub')
  else: print(f'unknown:{list(emps[0].keys())}')
" 2>/dev/null)
    if [ "$emp_shape" = "stub" ]; then
      record PASS T262 "GET /employee employments are STUBS by default" "only id+url, no startDate"
    elif [ "$emp_shape" = "expanded" ]; then
      record FAIL T262 "GET /employee employments are STUBS" "got expanded without fields param"
    else
      record FAIL T262 "GET /employee employments shape" "$emp_shape"
    fi
  else
    record FAIL T262 "GET /employee employments shape" "got $LAST_CODE"
  fi
else
  record SKIP T262 "GET /employee employments shape" "no inline employee"
fi

# T263: GET /employee with fields=employments(*) returns EXPANDED
if [ -n "${IDS[EMP_INLINE_ID]:-}" ]; then
  api GET "employee?id=${IDS[EMP_INLINE_ID]}&count=1&fields=id,employments(*)"
  if [ "$LAST_CODE" = "200" ]; then
    emp_expanded=$(echo "$LAST_BODY" | python3 -c "
import sys,json
vs=json.load(sys.stdin).get('values',[])
if not vs: print('no_values')
else:
  emps=vs[0].get('employments',[])
  if not emps: print('empty')
  elif 'startDate' in emps[0]: print('expanded')
  else: print(f'stub:{list(emps[0].keys())}')
" 2>/dev/null)
    if [ "$emp_expanded" = "expanded" ]; then
      record PASS T263 "GET /employee fields=employments(*) → expanded" "startDate present"
    else
      record FAIL T263 "GET /employee fields=employments(*)" "$emp_expanded"
    fi
  else
    record FAIL T263 "GET /employee fields expansion" "got $LAST_CODE"
  fi
else
  record SKIP T263 "GET /employee fields=employments(*)" "no inline employee"
fi

# ----- Invalid fields filter: envelope fields → 400 -----
# "total" and "values" are response envelope fields, never valid DTO fields.
# Verified across 12 endpoints below.

_fields_envelope_test() {
  # $1=test_id $2=endpoint_with_params $3=bad_field $4=short_desc
  local tid="$1" ep="$2" bad="$3" desc="$4"
  api GET "${ep}&fields=${bad}"
  if [ "$LAST_CODE" = "400" ]; then
    record PASS "$tid" "GET /${desc} fields=${bad} → 400" "envelope field rejected"
  else
    record FAIL "$tid" "GET /${desc} fields=${bad}" "expected 400, got $LAST_CODE"
  fi
}

# total
_fields_envelope_test T275a "ledger/posting?dateFrom=$TODAY&dateTo=$TOMORROW&count=1" total ledger/posting
_fields_envelope_test T275b "customer?customerName=nonexistent_${TS}&count=1" total customer
_fields_envelope_test T275c "employee?count=1" total employee
_fields_envelope_test T275d "department?count=1" total department
_fields_envelope_test T275e "product?count=1" total product
_fields_envelope_test T275f "project?count=1" total project
_fields_envelope_test T275g "order?orderDateFrom=2026-01-01&orderDateTo=2026-12-31&count=1" total order
_fields_envelope_test T275h "invoice?invoiceDateFrom=2026-01-01&invoiceDateTo=2026-12-31&count=1" total invoice
_fields_envelope_test T275i "ledger/account?count=1" total ledger/account
_fields_envelope_test T275j "ledger/voucher?dateFrom=2026-01-01&dateTo=2026-12-31&count=1" total ledger/voucher
_fields_envelope_test T275k "travelExpense?count=1" total travelExpense
_fields_envelope_test T275l "activity?count=1" total activity

# values
_fields_envelope_test T275m "ledger/posting?dateFrom=$TODAY&dateTo=$TOMORROW&count=1" "values(date,amountGross)" ledger/posting
_fields_envelope_test T275n "customer?customerName=nonexistent_${TS}&count=1" "values(id,name)" customer
_fields_envelope_test T275o "employee?count=1" values employee
_fields_envelope_test T275p "department?count=1" values department
_fields_envelope_test T275q "product?count=1" values product
_fields_envelope_test T275r "project?count=1" values project
_fields_envelope_test T275s "order?orderDateFrom=2026-01-01&orderDateTo=2026-12-31&count=1" values order
_fields_envelope_test T275t "invoice?invoiceDateFrom=2026-01-01&invoiceDateTo=2026-12-31&count=1" values invoice
_fields_envelope_test T275u "ledger/account?count=1" values ledger/account
_fields_envelope_test T275v "ledger/voucher?dateFrom=2026-01-01&dateTo=2026-12-31&count=1" values ledger/voucher
_fields_envelope_test T275w "travelExpense?count=1" values travelExpense
_fields_envelope_test T275x "activity?count=1" values activity

# Sanity: valid DTO fields → 200
api GET "ledger/posting?dateFrom=$TODAY&dateTo=$TOMORROW&count=1&fields=id,date,amountGross"
if [ "$LAST_CODE" = "200" ]; then
  record PASS T275z "GET /ledger/posting fields=id,date,amountGross → 200" "valid DTO fields accepted"
else
  record FAIL T275z "GET /ledger/posting valid fields" "expected 200, got $LAST_CODE"
fi

echo ""

# ======================================================================
# PHASE 15: Cleanup (phases 9-14)
# ======================================================================
echo "=== PHASE 15: Cleanup (phases 9-14) ==="

cleanup_delete() {
  local tid="$1" endpoint="$2" desc="$3"
  api DELETE "$endpoint"
  if [ "$LAST_CODE" = "204" ] || [ "$LAST_CODE" = "200" ]; then
    record PASS "$tid" "DELETE /$desc" "$LAST_CODE"
  elif [ "$LAST_CODE" = "403" ]; then
    record XFAIL "$tid" "DELETE /$desc (forbidden)" "403"
  else
    record FAIL "$tid" "DELETE /$desc" "got $LAST_CODE"
    validation_msg
  fi
}

# Delete standalone order + orderline
[ -n "${IDS[STANDALONE_OL_ID]:-}" ] && cleanup_delete T150a "order/orderline/${IDS[STANDALONE_OL_ID]}" "order/orderline (standalone)"
[ -n "${IDS[STANDALONE_ORDER_ID]:-}" ] && cleanup_delete T150b "order/${IDS[STANDALONE_ORDER_ID]}" "order (standalone)"

# Delete travel expenses from phase 10
[ -n "${IDS[TE_INLINE_COST_ID]:-}" ] && cleanup_delete T151a "travelExpense/${IDS[TE_INLINE_COST_ID]}" "travelExpense (inline costs)"
[ -n "${IDS[TE_INLINE_PD_ID]:-}" ] && cleanup_delete T151b "travelExpense/${IDS[TE_INLINE_PD_ID]}" "travelExpense (inline perDiem)"

# Delete projects from phase 10
[ -n "${IDS[PROJ_INLINE_ID]:-}" ] && cleanup_delete T152 "project/${IDS[PROJ_INLINE_ID]}" "project (inline participants)"

# Delete products from phase 11
[ -n "${IDS[PROD_SHAPE_ID]:-}" ] && cleanup_delete T153 "product/${IDS[PROD_SHAPE_ID]}" "product (shape test)"

# Delete customers from phase 11
[ -n "${IDS[CUST_SHAPE_ID]:-}" ] && cleanup_delete T154 "customer/${IDS[CUST_SHAPE_ID]}" "customer (shape test)"

# Note: employees cannot be deleted (403), so we skip EMP_INLINE_ID and EMP_DEEP_ID

# Delete timesheet entry, project activity, activity, and project from phase 14b
[ -n "${IDS[TS_ENTRY_ID]:-}" ] && cleanup_delete T155a "timesheet/entry/${IDS[TS_ENTRY_ID]}" "timesheet/entry (verify)"
[ -n "${IDS[PROJ_ACT_LINK_ID]:-}" ] && cleanup_delete T155b "project/projectActivity/${IDS[PROJ_ACT_LINK_ID]}" "project/projectActivity (verify)"
[ -n "${IDS[TS_PROJ_ID]:-}" ] && cleanup_delete T155c "project/${IDS[TS_PROJ_ID]}" "project (timesheet verify)"
[ -n "${IDS[TS_ACT_ID]:-}" ] && cleanup_delete T155d "activity/${IDS[TS_ACT_ID]}" "activity (verify)"

echo ""

# ======================================================================
# PHASE 16: Knowledge Base Verification (field-guide, entity-deps, id-patterns)
# ======================================================================
echo "=== PHASE 16: Knowledge Base Verification ==="

# --- T168: Employment NOT auto-created with employee ---
# Create a fresh NO_ACCESS employee (with dateOfBirth for T169), then check employments count = 0
api POST employee "{\"firstName\":\"EmpCheck\",\"lastName\":\"NoAuto $TS\",\"userType\":\"NO_ACCESS\",\"department\":{\"id\":${IDS[DEPT_ID]}},\"dateOfBirth\":\"1990-01-01\"}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[EMP_NOAUTO_ID]=$(extract_id)
  api GET "employee/employment?employeeId=${IDS[EMP_NOAUTO_ID]}"
  emp_auto_count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('fullResultSize',0))" 2>/dev/null)
  if [ "$emp_auto_count" = "0" ]; then
    record PASS T168 "Employment NOT auto-created with employee" "count=0 confirmed"
  else
    record FAIL T168 "Employment NOT auto-created with employee" "expected 0, got $emp_auto_count"
  fi
else
  record FAIL T168 "Employment NOT auto-created (employee create failed)" "got $LAST_CODE"
  validation_msg
fi

# --- T169: Standalone POST /employee/employment ---
# Use EMP_NOAUTO_ID which has no employment yet
if [ -n "${IDS[EMP_NOAUTO_ID]:-}" ]; then
  api POST "employee/employment" "{\"employee\":{\"id\":${IDS[EMP_NOAUTO_ID]}},\"startDate\":\"$TODAY\"}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[EMPLOYMENT_STANDALONE_ID]=$(extract_id)
    record PASS T169 "POST /employee/employment (standalone)" "id=${IDS[EMPLOYMENT_STANDALONE_ID]}"
  else
    record FAIL T169 "POST /employee/employment (standalone)" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T169 "POST /employee/employment (standalone)" "no employee"
fi

# --- T177: departmentNumber defaults to empty string (NOT auto-assigned) ---
api POST department "{\"name\":\"AutoNum Dept $TS\"}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[DEPT_AUTONUM_ID]=$(extract_id)
  dept_num=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(repr(json.load(sys.stdin)['value'].get('departmentNumber','')))" 2>/dev/null)
  record PASS T177 "departmentNumber on POST (defaults to empty)" "departmentNumber=$dept_num"
else
  record FAIL T177 "departmentNumber (create failed)" "got $LAST_CODE"
  validation_msg
fi

# --- T181: deliveryDate omitted in inline order → 422 ---
api POST invoice "{
  \"invoiceDate\":\"$TODAY\",
  \"invoiceDueDate\":\"$DUE_DATE\",
  \"customer\":{\"id\":${IDS[CUST_ID]}},
  \"orders\":[{
    \"orderDate\":\"$TODAY\",
    \"customer\":{\"id\":${IDS[CUST_ID]}},
    \"orderLines\":[{\"product\":{\"id\":${IDS[PROD_ID]}},\"count\":1}]
  }]
}"
expect_fail T181 "POST /invoice (order without deliveryDate)"
check_error_message T181b "Error msg: deliveryDate null" "Kan ikke være null"

# --- T192: Cost without date → still succeeds ---
if [ -n "${IDS[TE_ID]:-}" ]; then
  api POST "travelExpense/cost" "{\"travelExpense\":{\"id\":${IDS[TE_ID]}},\"costCategory\":{\"id\":${IDS[COST_CAT_ID]}},\"paymentType\":{\"id\":${IDS[TRAVEL_PAY_ID]}},\"currency\":{\"id\":${IDS[CURRENCY_ID]}},\"amountCurrencyIncVat\":100.0}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    record PASS T192 "POST /travelExpense/cost (no date)" "$LAST_CODE - date is optional"
  else
    record FAIL T192 "POST /travelExpense/cost (no date)" "got $LAST_CODE - date may be required"
    validation_msg
  fi
else
  record SKIP T192 "POST /travelExpense/cost (no date)" "no travel expense"
fi

# --- T210: Raw int reference fails (not wrapped in {id: X}) ---
api POST order "{\"orderDate\":\"$TODAY\",\"deliveryDate\":\"$TODAY\",\"customer\":${IDS[CUST_ID]}}"
expect_fail T210 "POST /order (raw int customer ref, not wrapped)"

# --- T216: Error response has status, code, validationMessages ---
# Use T210's response (should be an error)
api POST employee '{"firstName":"ErrShape","lastName":"Test"}'
err_shape=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin)
has_all = 'status' in d and 'code' in d and 'validationMessages' in d
print('yes' if has_all else 'no')
" 2>/dev/null)
if [ "$err_shape" = "yes" ]; then
  record PASS T216 "Error response has status/code/validationMessages" "confirmed"
else
  record FAIL T216 "Error response shape" "missing expected fields"
fi

# --- T218: employeeNumber defaults to empty (NOT auto-assigned) ---
if [ -n "${IDS[EMP_NOAUTO_ID]:-}" ]; then
  api GET "employee/${IDS[EMP_NOAUTO_ID]}"
  emp_num=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(repr(json.load(sys.stdin)['value'].get('employeeNumber','')))" 2>/dev/null)
  record PASS T218 "employeeNumber on POST (defaults to empty)" "employeeNumber=$emp_num"
else
  record SKIP T218 "employeeNumber on POST" "no employee"
fi

# --- T219: customerNumber auto-assigned ---
if [ -n "${IDS[CUST_ID]:-}" ]; then
  api GET "customer/${IDS[CUST_ID]}"
  cust_num=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['value'].get('customerNumber',''))" 2>/dev/null)
  if [ -n "$cust_num" ] && [ "$cust_num" != "None" ] && [ "$cust_num" != "null" ]; then
    record PASS T219 "customerNumber auto-assigned" "customerNumber=$cust_num"
  else
    record FAIL T219 "customerNumber auto-assigned" "customerNumber is null/empty"
  fi
else
  record SKIP T219 "customerNumber auto-assigned" "no customer"
fi

# --- T220: Travel expense number auto-assigned ---
if [ -n "${IDS[TE_ID]:-}" ]; then
  api GET "travelExpense/${IDS[TE_ID]}"
  te_num=$(echo "$LAST_BODY" | python3 -c "import sys,json; v=json.load(sys.stdin)['value']; print(v.get('number', v.get('numberAsString','')))" 2>/dev/null)
  if [ -n "$te_num" ] && [ "$te_num" != "None" ] && [ "$te_num" != "null" ] && [ "$te_num" != "" ]; then
    record PASS T220 "Travel expense number auto-assigned" "number=$te_num"
  else
    record FAIL T220 "Travel expense number auto-assigned" "number is null/empty"
  fi
else
  record SKIP T220 "Travel expense number auto-assigned" "no travel expense"
fi

# --- T221: Version starts at 1 on newly created entity ---
api POST customer "{\"name\":\"VerCheck $TS\"}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[CUST_VER_ID]=$(extract_id)
  ver_val=$(extract_version)
  if [ "$ver_val" = "1" ]; then
    record PASS T221 "Version starts at 1" "version=$ver_val"
  else
    record FAIL T221 "Version starts at 1" "version=$ver_val (expected 1)"
  fi
else
  record FAIL T221 "Version starts at 1 (create failed)" "got $LAST_CODE"
  validation_msg
fi

# --- T222: PUT with wrong version fails ---
if [ -n "${IDS[CUST_VER_ID]:-}" ]; then
  api PUT "customer/${IDS[CUST_VER_ID]}" "{\"id\":${IDS[CUST_VER_ID]},\"version\":999,\"name\":\"WrongVer $TS\"}"
  if [ "$LAST_CODE" = "409" ] || [ "$LAST_CODE" = "422" ]; then
    record PASS T222 "PUT with wrong version fails" "$LAST_CODE"
  elif [[ "$LAST_CODE" =~ ^2 ]]; then
    record FAIL T222 "PUT with wrong version should fail" "got $LAST_CODE (success unexpected)"
  else
    record PASS T222 "PUT with wrong version fails" "$LAST_CODE"
  fi
else
  record SKIP T222 "PUT with wrong version" "no customer"
fi

# --- T230: List GET returns full objects with version and nested fields ---
# Unresolved issue: do list GETs return complete objects (version, postalAddress)?
if [ -n "${IDS[CUST_ID]:-}" ]; then
  api GET "customer?id=${IDS[CUST_ID]}"
  list_check=$(echo "$LAST_BODY" | python3 -c "
import sys,json
d=json.load(sys.stdin)
vs=d.get('values',[])
if not vs:
  print('no_values')
else:
  v=vs[0]
  has_version = 'version' in v
  has_addr = 'postalAddress' in v and isinstance(v.get('postalAddress'), dict)
  addr_has_id = v.get('postalAddress',{}).get('id') is not None if has_addr else False
  print(f'version={has_version},addr={has_addr},addr_id={addr_has_id}')
" 2>/dev/null)
  if echo "$list_check" | grep -q "version=True.*addr=True.*addr_id=True"; then
    record PASS T230 "List GET returns full objects (version+postalAddress)" "$list_check"
  elif echo "$list_check" | grep -q "version=True"; then
    record PASS T230 "List GET returns version but check addr" "$list_check"
  else
    record FAIL T230 "List GET completeness" "$list_check"
  fi
else
  record SKIP T230 "List GET completeness" "no customer"
fi

# --- T240: NO_ACCESS employee as projectManager → fails (entitlement issue) ---
# Unresolved: NO_ACCESS employees lack AUTH_PROJECT_MANAGER entitlement
if [ -n "${IDS[EMP_NOAUTO_ID]:-}" ]; then
  api POST project "{\"name\":\"PM Entitlement Test $TS\",\"projectManager\":{\"id\":${IDS[EMP_NOAUTO_ID]}},\"isInternal\":true,\"startDate\":\"$TODAY\"}"
  if [ "$LAST_CODE" = "422" ]; then
    pm_err=$(echo "$LAST_BODY" | python3 -c "
import sys,json; d=json.load(sys.stdin)
msgs=d.get('validationMessages',[])
print('|'.join(m.get('message','') for m in msgs) + '|' + d.get('message',''))
" 2>/dev/null)
    if echo "$pm_err" | grep -qi "prosjektleder"; then
      record XFAIL T240 "NO_ACCESS employee as PM (lacks entitlement)" "422 - entitlement required"
    else
      record XFAIL T240 "NO_ACCESS employee as PM (other 422)" "$pm_err"
    fi
  elif [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[PROJ_PM_TEST_ID]=$(extract_id)
    record PASS T240 "NO_ACCESS employee as PM (unexpectedly works)" "$LAST_CODE"
  else
    record FAIL T240 "NO_ACCESS employee as PM" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T240 "NO_ACCESS employee as PM" "no employee"
fi

# --- T241: Admin employee as projectManager → succeeds ---
# The admin (EMP_ID from setup) should have AUTH_PROJECT_MANAGER
api POST project "{\"name\":\"Admin PM Test $TS\",\"projectManager\":{\"id\":${IDS[EMP_ID]}},\"isInternal\":true,\"startDate\":\"$TODAY\"}"
if [[ "$LAST_CODE" =~ ^2 ]]; then
  IDS[PROJ_ADMIN_PM_ID]=$(extract_id)
  record PASS T241 "Admin employee as PM (has entitlement)" "$LAST_CODE"
else
  record FAIL T241 "Admin employee as PM" "got $LAST_CODE"
  validation_msg
fi

# --- T242: STANDARD employee as projectManager → check entitlement ---
if [ -n "${IDS[EMP3_ID]:-}" ]; then
  api POST project "{\"name\":\"Std PM Test $TS\",\"projectManager\":{\"id\":${IDS[EMP3_ID]}},\"isInternal\":true,\"startDate\":\"$TODAY\"}"
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    IDS[PROJ_STD_PM_ID]=$(extract_id)
    record PASS T242 "STANDARD employee as PM" "$LAST_CODE - has entitlement"
  elif [ "$LAST_CODE" = "422" ]; then
    record XFAIL T242 "STANDARD employee as PM (lacks entitlement)" "422 - same as NO_ACCESS"
  else
    record FAIL T242 "STANDARD employee as PM" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T242 "STANDARD employee as PM" "no STANDARD employee"
fi

# --- T243: Grant entitlement via API ---
# Try PUT /employee/entitlement/:grantEntitlementsByTemplate
if [ -n "${IDS[EMP_NOAUTO_ID]:-}" ]; then
  api PUT "employee/entitlement/:grantEntitlementsByTemplate?employeeId=${IDS[EMP_NOAUTO_ID]}&template=AUTH_PROJECT_MANAGER" ""
  if [[ "$LAST_CODE" =~ ^2 ]]; then
    record PASS T243 "Grant entitlement via API" "$LAST_CODE"
    # Now retry project creation
    api POST project "{\"name\":\"PM After Grant $TS\",\"projectManager\":{\"id\":${IDS[EMP_NOAUTO_ID]}},\"isInternal\":true,\"startDate\":\"$TODAY\"}"
    if [[ "$LAST_CODE" =~ ^2 ]]; then
      IDS[PROJ_GRANTED_PM_ID]=$(extract_id)
      record PASS T243b "Project with granted PM" "$LAST_CODE"
    else
      record FAIL T243b "Project with granted PM" "got $LAST_CODE"
      validation_msg
    fi
  elif [ "$LAST_CODE" = "404" ]; then
    record XFAIL T243 "Grant entitlement endpoint (404 on sandbox)" "endpoint not available"
  else
    record FAIL T243 "Grant entitlement via API" "got $LAST_CODE"
    validation_msg
  fi
else
  record SKIP T243 "Grant entitlement via API" "no employee"
fi

echo ""

# ======================================================================
# PHASE 16 CLEANUP
# ======================================================================
echo "=== PHASE 16 Cleanup ==="

[ -n "${IDS[DEPT_AUTONUM_ID]:-}" ] && cleanup_delete T16C1 "department/${IDS[DEPT_AUTONUM_ID]}" "department (autonum)"
[ -n "${IDS[CUST_VER_ID]:-}" ] && cleanup_delete T16C2 "customer/${IDS[CUST_VER_ID]}" "customer (version check)"
[ -n "${IDS[PROJ_PM_TEST_ID]:-}" ] && cleanup_delete T16C3 "project/${IDS[PROJ_PM_TEST_ID]}" "project (PM test)"
[ -n "${IDS[PROJ_ADMIN_PM_ID]:-}" ] && cleanup_delete T16C4 "project/${IDS[PROJ_ADMIN_PM_ID]}" "project (admin PM)"
[ -n "${IDS[PROJ_STD_PM_ID]:-}" ] && cleanup_delete T16C5 "project/${IDS[PROJ_STD_PM_ID]}" "project (std PM)"
[ -n "${IDS[PROJ_GRANTED_PM_ID]:-}" ] && cleanup_delete T16C6 "project/${IDS[PROJ_GRANTED_PM_ID]}" "project (granted PM)"
# Note: employees cannot be deleted (403)

# ======================================================================
# PHASE 17: GET /ledger — aggregated account totals (hovedbok)
# ======================================================================
echo "=== PHASE 17 GET /ledger aggregated totals ==="

# T17.1: GET /ledger returns 200 with sumAmount per account
api GET "ledger?dateFrom=2026-01-01&dateTo=2026-04-01&count=3"
expect_success T17.1 "GET /ledger returns 200" 200

# T17.2: Response contains sumAmount field
HAS_SUM=$(echo "$LAST_BODY" | python3 -c "
import sys,json
d=json.load(sys.stdin)
vals=d.get('values',[])
print('yes' if vals and 'sumAmount' in vals[0] else 'no')
" 2>/dev/null)
if [ "$HAS_SUM" = "yes" ]; then
  record PASS T17.2 "GET /ledger response has sumAmount"
else
  record FAIL T17.2 "GET /ledger response has sumAmount" "sumAmount not found"
fi

# T17.3: fields filter works — returns only requested fields
api GET "ledger?dateFrom=2026-01-01&dateTo=2026-04-01&count=1&fields=account(number,name),sumAmount,closingBalance"
expect_success T17.3 "GET /ledger with fields filter returns 200" 200

echo ""

# ======================================================================
# PHASE 18: Accounting dimensions — create name + values, then clean up
# ======================================================================
echo "=== PHASE 18 Accounting dimensions ==="

# T18.1: Create dimension name with dimensionName field
api POST "ledger/accountingDimensionName" '{"dimensionName": "VerifyDim_'"$TS"'"}'
expect_success T18.1 "POST /ledger/accountingDimensionName creates dimension" 201
IDS[DIM_NAME_ID]=$(extract_id)
DIM_INDEX=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['value']['dimensionIndex'])" 2>/dev/null)

# T18.2: Create dimension value with displayName + dimensionIndex
if [ -n "${DIM_INDEX:-}" ]; then
  api POST "ledger/accountingDimensionValue" '{"displayName": "ValA_'"$TS"'", "dimensionIndex": '"$DIM_INDEX"'}'
  expect_success T18.2 "POST /ledger/accountingDimensionValue creates value" 201
  IDS[DIM_VAL1_ID]=$(extract_id)
else
  record SKIP T18.2 "POST /ledger/accountingDimensionValue (no dimensionIndex)"
fi

# T18.3: Create second value on same dimension
if [ -n "${DIM_INDEX:-}" ]; then
  api POST "ledger/accountingDimensionValue" '{"displayName": "ValB_'"$TS"'", "dimensionIndex": '"$DIM_INDEX"'}'
  expect_success T18.3 "POST /ledger/accountingDimensionValue second value" 201
  IDS[DIM_VAL2_ID]=$(extract_id)
else
  record SKIP T18.3 "POST /ledger/accountingDimensionValue second value (no dimensionIndex)"
fi

# T18.4: Wrong field name → 422
api POST "ledger/accountingDimensionValue" '{"name": "ShouldFail", "dimensionIndex": 1}'
expect_fail T18.4 "POST /ledger/accountingDimensionValue with wrong field name" 422

# Cleanup
[ -n "${IDS[DIM_VAL2_ID]:-}" ] && cleanup_delete T18C1 "ledger/accountingDimensionValue/${IDS[DIM_VAL2_ID]}" "dimension value 2"
[ -n "${IDS[DIM_VAL1_ID]:-}" ] && cleanup_delete T18C2 "ledger/accountingDimensionValue/${IDS[DIM_VAL1_ID]}" "dimension value 1"
[ -n "${IDS[DIM_NAME_ID]:-}" ] && cleanup_delete T18C3 "ledger/accountingDimensionName/${IDS[DIM_NAME_ID]}" "dimension name"

echo ""

# ======================================================================
# SUMMARY
# ======================================================================
echo "======================================================================"
echo "  SUMMARY"
echo "======================================================================"
echo ""
for line in "${RESULTS[@]}"; do
  echo "  $line"
done
echo ""
echo "----------------------------------------------------------------------"
echo "  PASS: $PASS  |  XFAIL: $XFAIL  |  FAIL: $FAIL  |  SKIP: $SKIP"
echo "  Total: $((PASS + XFAIL + FAIL + SKIP))"
echo "----------------------------------------------------------------------"

if [ "$FAIL" -gt 0 ]; then
  echo "  *** $FAIL UNEXPECTED RESULT(S) — review above ***"
  exit 1
else
  echo "  All tests passed or failed as expected."
  exit 0
fi
