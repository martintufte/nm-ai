# Example Tasks by API Flow Pattern

Task prompts organized by the 5 core API flow patterns. Each task has a natural-language prompt (as a user/competition would phrase it) and a separate expected flow section for validation.

---

## Pattern 1: Create Single Entity

A single POST, possibly with inline sub-resources or a prerequisite lookup.

### Task 1.1 — Create Employee (Norwegian Bokmål)

**Prompt:**
> Opprett en ansatt ved navn Ola Nordmann, født 15. mars 1988, e-post ola.nordmann@firma.no, startdato 1. april 2026.

**Expected flow:**
1. `GET /department?count=1` — need a department ID (required for employee creation)
2. `POST /employee` with `firstName`, `lastName`, `dateOfBirth`, `email`, `userType: "STANDARD"`, `department: {id}`, `employments: [{startDate: "2026-04-01"}]`

**Call count:** 2

---

## Pattern 2: Create with Linking

Multiple entities must exist (or be created) before the final entity. Involves lookups, possible creation of prerequisites, and a composite POST.

### Task 2.1 — Create Invoice (English)

**Prompt:**
> Create an invoice dated March 25, 2026 due April 25, 2026 for customer "Berge AS" with 3 units of product "Kontorstol" at 2500 kr each.

**Expected flow:**
1. `GET /customer?name=Berge AS` — check if exists; if not → `POST /customer {"name": "Berge AS"}`
2. `GET /product?name=Kontorstol` — check if exists; if not → `POST /product {"name": "Kontorstol", "priceExcludingVatCurrency": 2500}`
3. `GET /ledger/account?isBankAccount=true` → `PUT /ledger/account/{id}` to ensure bank account number is set
4. `POST /invoice` with inline order and orderLines (`count: 3`, product ref, customer ref, dates)

**Call count:** 4–6 (depending on whether customer/product already exist and bank account needs setup)

---

## Pattern 3: Modify Existing

Look up an entity, then PUT to update it. Requires `id` and `version` from the GET.

### Task 3.1 — Update Customer Address (French)

**Prompt:**
> Le client "Fjord Consulting" a déménagé. Mettez à jour son adresse à Storgata 45, 0182 Oslo.

**Expected flow:**
1. `GET /customer?name=Fjord Consulting` — get `id` and `version`
2. `PUT /customer/{id}` with `id`, `version`, `name`, and `postalAddress: {addressLine1: "Storgata 45", postalCode: "0182", city: "Oslo"}`

**Call count:** 2

---

## Pattern 4: Delete/Reverse

Look up an entity, then DELETE it.

### Task 4.1 — Delete Department (German)

**Prompt:**
> Bitte löschen Sie die Abteilung "Temporary Projects".

**Expected flow:**
1. `GET /department?name=Temporary Projects` — get `id`
2. `DELETE /department/{id}`

**Call count:** 2

---

## Pattern 5: Multi-step Setup

Chain of creates and actions across multiple entity types, ending with a composite operation.

### Task 5.1 — Full Invoice with Payment (Spanish)

**Prompt:**
> Cree un cliente "Nordic Solutions AS", un producto "Consultoría TI" a 1200 kr, y genere una factura con fecha 20 de marzo de 2026, vencimiento 20 de abril de 2026, con 10 unidades del producto. Luego registre el pago completo con fecha 20 de marzo de 2026.

**Expected flow:**
1. `POST /customer` — create "Nordic Solutions AS"
2. `POST /product` — create "Consultoría TI" with price 1200
3. `GET /ledger/account?isBankAccount=true` → `PUT /ledger/account/{id}` — ensure bank account number
4. `POST /invoice` — with inline order (10 units, customer ref, product ref, dates)
5. `GET /invoice/paymentType` — look up payment type ID
6. `PUT /invoice/{id}/:payment?paymentDate=2026-03-20&paymentTypeId=X&paidAmount=12000.0`

**Call count:** 5–7
