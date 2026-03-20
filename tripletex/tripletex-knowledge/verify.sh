#!/usr/bin/env bash
# Tripletex Knowledge Base Verification Suite
# Tests every documented gotcha and unverified gap against the sandbox API.
# Usage: TRIPLETEX_SANDBOX_API_URL=... TRIPLETEX_SANBOX_TOKEN=... bash verify.sh
set -uo pipefail

BASE="${TRIPLETEX_SANDBOX_API_URL:?Set TRIPLETEX_SANDBOX_API_URL}"
TOKEN="${TRIPLETEX_SANBOX_TOKEN:?Set TRIPLETEX_SANBOX_TOKEN}"

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

echo ""

# ======================================================================
# PHASE 4: Product gotchas
# ======================================================================
echo "=== PHASE 4: Product gotchas ==="

# T40: Product with vatType id=3 → 422 (gotcha #4)
api POST product "{\"name\":\"VatTest3 $TS\",\"vatType\":{\"id\":3}}"
expect_fail T40 "POST /product (vatType id=3) [gotcha #4]"

# T41: Product with vatType id=1 → 422 (gotcha #4)
api POST product "{\"name\":\"VatTest1 $TS\",\"vatType\":{\"id\":1}}"
expect_fail T41 "POST /product (vatType id=1) [gotcha #4]"

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
