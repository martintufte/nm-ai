# Synthetic Tasks by API Flow Pattern

Task prompts organized by the 5 core API flow patterns. Each task has a natural-language prompt (as a user/competition would phrase it) and a separate expected flow section for validation. Languages vary across Norwegian Bokmål, English, Spanish, Portuguese, Nynorsk, German, and French.

---

## Pattern 1: Create Single Entity

A single POST, possibly with a prerequisite lookup.

### Task 1.1 — Create Employee (Norwegian Bokmål)

**Prompt:**
> Opprett en ansatt ved navn Ola Nordmann, født 15. mars 1988, e-post ola.nordmann@firma.no, startdato 1. april 2026.

**Expected flow:**
1. `GET /department?count=1` — need a department ID (required for employee creation)
2. `POST /employee` with `firstName`, `lastName`, `dateOfBirth`, `email`, `userType: "STANDARD"`, `department: {id}`, `employments: [{startDate: "2026-04-01"}]`

**Call count:** 2

---

### Task 1.2 — Create Customer (English)

**Prompt:**
> Create a new customer "Havnevik Shipping AS" with organization number 987654321, email kontakt@havnevik.no, and postal address Sjøgata 12, 8006 Bodø.

**Expected flow:**
1. `POST /customer` with `name`, `organizationNumber`, `email`, inline `postalAddress: {addressLine1, postalCode, city}`

**Call count:** 1

---

### Task 1.3 — Create Product (German)

**Prompt:**
> Erstellen Sie ein Produkt namens "Ergonomischer Bürostuhl" mit einem Preis von 4500 kr (exkl. MwSt.).

**Expected flow:**
1. `POST /product` with `name: "Ergonomischer Bürostuhl"`, `priceExcludingVatCurrency: 4500`

**Call count:** 1

---

### Task 1.4 — Create Department (Portuguese)

**Prompt:**
> Crie um novo departamento chamado "Logística e Distribuição".

**Expected flow:**
1. `POST /department` with `name: "Logística e Distribuição"`

**Call count:** 1

---

### Task 1.5 — Create Employee Without Login (Nynorsk)

**Prompt:**
> Opprett ein tilsett som heiter Kari Haugen. Ho treng ikkje tilgang til systemet. Avdelinga er "Lager".

**Expected flow:**
1. `GET /department?name=Lager` — look up department
2. `POST /employee` with `firstName: "Kari"`, `lastName: "Haugen"`, `userType: "NO_ACCESS"`, `department: {id}`

**Call count:** 2

---

### Task 1.6 — Create Activity (French)

**Prompt:**
> Créez une activité de projet appelée "Conception UX" facturable.

**Expected flow:**
1. `POST /activity` with `name: "Conception UX"`, `activityType: "PROJECT_GENERAL_ACTIVITY"`, `isChargeable: true`

**Call count:** 1

---

### Task 1.7 — Create Customer with Category (Spanish)

**Prompt:**
> Cree un cliente llamado "Montaña Verde AS" con número de organización 912345678 y correo electrónico info@montanaverde.no. Es un cliente privado.

**Expected flow:**
1. `POST /customer` with `name`, `organizationNumber`, `email`, `isPrivateIndividual: true`

**Call count:** 1

---

### Task 1.8 — Create Employee with Full Employment Details (English)

**Prompt:**
> Create an employee Erik Solberg, born 1990-06-22, email erik.solberg@firma.no, in the "Utvikling" department with a start date of 2026-05-01, employment type ORDINARY, and permanent employment form.

**Expected flow:**
1. `GET /department?name=Utvikling` — look up department
2. `POST /employee` with `firstName`, `lastName`, `dateOfBirth`, `email`, `userType: "STANDARD"`, `department: {id}`, inline `employments: [{startDate: "2026-05-01", employmentDetails: [{date: "2026-05-01", employmentType: "ORDINARY", employmentForm: "PERMANENT"}]}]`

**Call count:** 2

---

## Pattern 2: Create with Linking

Multiple entities must exist (or be created) before the final entity. Involves lookups, possible creation of prerequisites, and a composite POST.

### Task 2.1 — Create Invoice (English)

**Prompt:**
> Create an invoice dated March 25, 2026 due April 25, 2026 for customer "Berge AS" with 3 units of product "Kontorstol" at 2500 kr each.

**Expected flow:**
1. `GET /customer?customerName=Berge AS` — check if exists; if not → `POST /customer {"name": "Berge AS"}`
2. `GET /product?name=Kontorstol` — check if exists; if not → `POST /product {"name": "Kontorstol", "priceExcludingVatCurrency": 2500}`
3. `GET /ledger/account?isBankAccount=true` → `PUT /ledger/account/{id}` to ensure bank account number is set
4. `POST /invoice` with inline order and orderLines (`count: 3`, product ref, customer ref, dates)

**Call count:** 4–6 (depending on whether customer/product already exist and bank account needs setup)

---

### Task 2.2 — Create Invoice for New Customer and Product (Norwegian Bokmål)

**Prompt:**
> Opprett en faktura for kunden "Nordfjord Bygg AS" med produktet "Sement 25kg" til 189 kr per enhet, 50 enheter. Fakturadato 1. april 2026, forfall 1. mai 2026.

**Expected flow:**
1. `POST /customer` — create "Nordfjord Bygg AS"
2. `POST /product` — create "Sement 25kg" with price 189
3. `POST /invoice` with inline order (50 units, customer ref, product ref, dates)

**Call count:** 3 (bank account assumed already set up, or +2 for setup)

---

### Task 2.3 — Create Project with Participant (English)

**Prompt:**
> Create the project "Upgrade Silveroak" linked to the customer "Silveroak AS". Add Alice Smith (alice@firma.no) as a participant on the project.

**Expected flow:**
1. `GET /customer?customerName=Silveroak AS` — look up pre-created customer
2. `GET /employee?firstName=Alice&lastName=Smith` — look up pre-created employee (participant)
3. `GET /token/session/>whoAmI` — get admin employee ID (for projectManager — requires AUTH_PROJECT_MANAGER entitlement)
4. `POST /project` — with `name`, `projectManager: {id: ADMIN_ID}`, `customer: {id}`, `isInternal: false`, `startDate`, and inline `participants: [{employee: {id: ALICE_ID}}]`

**Call count:** 4

**Note:** Only the admin employee has the `AUTH_PROJECT_MANAGER` entitlement. Creating employees with any `userType` does not grant it.

---

### Task 2.4 — Travel Expense with Cost (Spanish)

**Prompt:**
> Registre un gasto de viaje para el empleado "Lars Bakken" titulado "Conferencia Oslo". Viaje de ida el 10 de abril de 2026, vuelta el 12 de abril de 2026, desde Bergen a Oslo. Incluya un costo de taxi de 450 kr.

**Expected flow:**
1. `GET /employee?firstName=Lars&lastName=Bakken` — look up employee
2. `GET /travelExpense/costCategory?count=50` — find taxi category (id: 32947605)
3. `GET /travelExpense/paymentType` — get payment type ID (id: 32947574 "Privat utlegg")
4. `POST /travelExpense` with `employee: {id}`, `title`, `travelDetails: {departureDate, returnDate, isDayTrip: false, departureFrom: "Bergen", destination: "Oslo"}`, inline `costs: [{costCategory: {id}, paymentType: {id}, currency: {id: 1}, amountCurrencyIncVat: 450, date: "2026-04-10"}]`

**Call count:** 4
**Note:** costCategory and paymentType are reference data that must be looked up. Costs are inlined on the travel POST to save a separate call.

---

### Task 2.5 — Create Project with Activity and Timesheet (French)

**Prompt:**
> Créez un projet "Migration Cloud" avec l'activité "Développement" et enregistrez 7,5 heures de travail pour l'employé "Anna Berg" le 15 avril 2026.

**Expected flow:**
1. `GET /token/session/>whoAmI` — get admin employee ID for project manager
2. `GET /employee?firstName=Anna&lastName=Berg` — look up employee
3. `POST /activity` — create "Développement" with `activityType: "PROJECT_GENERAL_ACTIVITY"`
4. `POST /project` — with `name`, `projectManager: {id: ADMIN_ID}`, `isInternal: true`, `startDate`, inline `projectActivities: [{activity: {id: ACT_ID}}]`
5. `POST /timesheet/entry` — with `employee`, `project`, `activity`, `date: "2026-04-15"`, `hours: 7.5`

**Call count:** 5

---

### Task 2.6 — Create Order with Multiple Products (Portuguese)

**Prompt:**
> Crie um pedido para o cliente "Solvik Industri AS" com data de 1 de abril de 2026. Adicione 10 unidades do produto "Parafuso M8" e 5 unidades do produto "Porca M8".

**Expected flow:**
1. `GET /customer?customerName=Solvik Industri AS` — look up customer
2. `GET /product?name=Parafuso M8` — look up product 1
3. `GET /product?name=Porca M8` — look up product 2
4. `POST /order` — with `orderDate`, `deliveryDate`, `customer: {id}`, inline `orderLines: [{product: {id1}, count: 10}, {product: {id2}, count: 5}]`

**Call count:** 4

---

### Task 2.7 — Employee with Next of Kin (Norwegian Bokmål)

**Prompt:**
> Opprett en ansatt Ingrid Dahl, e-post ingrid.dahl@firma.no, i avdelingen "Salg". Legg til pårørende: ektefelle Per Dahl, telefon 98765432.

**Expected flow:**
1. `GET /department?name=Salg` — look up department
2. `POST /employee` — with `firstName: "Ingrid"`, `lastName: "Dahl"`, `email`, `userType: "STANDARD"`, `department: {id}`
3. `POST /employee/nextOfKin` — with `employee: {id}`, `name: "Per Dahl"`, `phoneNumber: "98765432"`, `typeOfRelationship: "SPOUSE"`

**Call count:** 3

---

### Task 2.8 — Accounting Voucher (English)

**Prompt:**
> Create a manual journal entry dated March 20, 2026 with description "Office supplies purchase". Debit account 6300 (Leie maskiner/inventar/IT-utstyr) for 2500 kr and credit account 1920 (Bank) for 2500 kr.

**Expected flow:**
1. `GET /ledger/account?number=6300&count=5` — get debit account ID
2. `GET /ledger/account?number=1920&count=5` — get credit account ID
3. `POST /ledger/voucher` — with `date`, `description`, `postings: [{date, account: {id: 6300_ID}, vatType: {id: 0}, amountGross: 2500, amountGrossCurrency: 2500, row: 1}, {date, account: {id: 1920_ID}, vatType: {id: 0}, amountGross: -2500, amountGrossCurrency: -2500, row: 2}]`

**Call count:** 3

---

## Pattern 3: Modify Existing

Look up an entity, then PUT to update it. Requires `id` and `version` from the GET.

### Task 3.1 — Update Customer Address (French)

**Prompt:**
> Le client "Fjord Consulting" a déménagé. Mettez à jour son adresse à Storgata 45, 0182 Oslo.

**Expected flow:**
1. `GET /customer?customerName=Fjord Consulting` — get `id` and `version`
2. `PUT /customer/{id}` with `id`, `version`, `postalAddress: {addressLine1: "Storgata 45", postalCode: "0182", city: "Oslo"}`

**Call count:** 2

---

### Task 3.2 — Update Employee Email (English)

**Prompt:**
> Update the email address of employee "Maren Solvang" to maren.solvang@nyepost.no.

**Expected flow:**
1. `GET /employee?firstName=Maren&lastName=Solvang` — get `id` and `version`
2. `PUT /employee/{id}` with `id`, `version`, `firstName`, `lastName`, `userType`, `department`, `email: "maren.solvang@nyepost.no"`

**Call count:** 2

---

### Task 3.3 — Update Product Price (Norwegian Bokmål)

**Prompt:**
> Produktet "Premium Kaffe 500g" har fått ny pris: 129 kr ekskl. mva.

**Expected flow:**
1. `GET /product?name=Premium Kaffe 500g` — get `id` and `version`
2. `PUT /product/{id}` with `id`, `version`, `name`, `priceExcludingVatCurrency: 129`

**Call count:** 2

---

### Task 3.4 — Update Customer Email and Phone (German)

**Prompt:**
> Aktualisieren Sie die E-Mail-Adresse des Kunden "Tromsø Tech AS" auf post@tromsotech.no und die Mobilnummer auf 41234567.

**Expected flow:**
1. `GET /customer?customerName=Tromsø Tech AS` — get `id` and `version`
2. `PUT /customer/{id}` with `id`, `version`, `email: "post@tromsotech.no"`, `phoneNumberMobile: "41234567"`

**Call count:** 2

---

### Task 3.5 — Set Employee Hourly Rate (Spanish)

**Prompt:**
> Establezca la tarifa horaria del empleado "Jonas Lie" en 650 kr, con un costo por hora de 400 kr, a partir del 1 de abril de 2026.

**Expected flow:**
1. `GET /employee?firstName=Jonas&lastName=Lie` — get employee ID
2. `POST /employee/hourlyCostAndRate` — with `employee: {id}`, `date: "2026-04-01"`, `rate: 650`, `hourCostRate: 400`

**Call count:** 2

---

### Task 3.6 — Update Project Customer (English)

**Prompt:**
> Change the customer on project "Warehouse Automation" to "Fjellberg Logistics AS".

**Expected flow:**
1. `GET /project?name=Warehouse Automation` — get project `id` and `version`
2. `GET /customer?customerName=Fjellberg Logistics AS` — get customer ID
3. `PUT /project/{id}` with `id`, `version`, `name`, `projectManager`, `startDate`, `customer: {id}`

**Call count:** 3

---

### Task 3.7 — Rename Department (Nynorsk)

**Prompt:**
> Endre namnet på avdelinga "Kundeservice" til "Kundeopplevelse".

**Expected flow:**
1. `GET /department?name=Kundeservice` — get `id` and `version`
2. `PUT /department/{id}` with `id`, `version`, `name: "Kundeopplevelse"`

**Call count:** 2

---

### Task 3.8 — Set Employee Standard Time (Portuguese)

**Prompt:**
> Defina o horário padrão do funcionário "Henrik Strand" para 7,5 horas por dia a partir de 1 de maio de 2026.

**Expected flow:**
1. `GET /employee?firstName=Henrik&lastName=Strand` — get employee ID
2. `POST /employee/standardTime` — with `employee: {id}`, `fromDate: "2026-05-01"`, `hoursPerDay: 7.5`

**Call count:** 2

---

## Pattern 4: Delete/Reverse

Look up an entity, then DELETE it or reverse it.

### Task 4.1 — Delete Department (German)

**Prompt:**
> Bitte löschen Sie die Abteilung "Temporary Projects".

**Expected flow:**
1. `GET /department?name=Temporary Projects` — get `id`
2. `DELETE /department/{id}`

**Call count:** 2

---

### Task 4.2 — Delete Travel Expense (Norwegian Bokmål)

**Prompt:**
> Slett reiseregningen med tittelen "Kundermøte Trondheim" for ansatt "Knut Pedersen".

**Expected flow:**
1. `GET /employee?firstName=Knut&lastName=Pedersen` — get employee ID
2. `GET /travelExpense?employeeId={empId}` — find travel expense
3. `DELETE /travelExpense/{id}`

**Call count:** 3

---

### Task 4.3 — Delete Customer (English)

**Prompt:**
> Delete the customer "Test Company AS" — it was created by mistake.

**Expected flow:**
1. `GET /customer?customerName=Test Company AS` — get `id`
2. `DELETE /customer/{id}`

**Call count:** 2

---

### Task 4.4 — Delete Product (French)

**Prompt:**
> Supprimez le produit "Ancien Modèle X100" du catalogue.

**Expected flow:**
1. `GET /product?name=Ancien Modèle X100` — get `id`
2. `DELETE /product/{id}`

**Call count:** 2

---

### Task 4.5 — Credit Note for Invoice (Spanish)

**Prompt:**
> Cree una nota de crédito para la factura del cliente "Vikingskip AS" con fecha 20 de marzo de 2026 y comentario "Factura incorrecta".

**Expected flow:**
1. `GET /customer?customerName=Vikingskip AS` — get customer ID
2. `GET /invoice?customerId={custId}&invoiceDateFrom=2026-01-01&invoiceDateTo=2026-12-31` — find invoice
3. `PUT /invoice/{id}/:createCreditNote?date=2026-03-20&comment=Factura incorrecta`

**Call count:** 3

---

### Task 4.6 — Delete Project (Portuguese)

**Prompt:**
> Exclua o projeto "Teste Piloto" — foi cancelado.

**Expected flow:**
1. `GET /project?name=Teste Piloto` — get `id`
2. `DELETE /project/{id}`

**Call count:** 2

---

### Task 4.7 — Reverse Voucher (English)

**Prompt:**
> Reverse the most recent voucher dated March 20, 2026 with description "Office supplies purchase".

**Expected flow:**
1. `GET /ledger/voucher?dateFrom=2026-03-20&dateTo=2026-03-20` — find voucher
2. `PUT /ledger/voucher/{id}/:reverse?date=2026-03-20`

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

---

### Task 5.2 — Travel Expense with Mileage and Per Diem (Norwegian Bokmål)

**Prompt:**
> Opprett en reiseregning for ansatt "Hilde Johansen" kalt "Kundebesøk Bergen". Reise fra Oslo til Bergen, avreise 5. april 2026 kl 07:00, retur 7. april 2026 kl 19:00. Legg til kjøregodtgjørelse for 463 km med egen bil, og diett for 2 overnattingsdøgn på hotell i Bergen.

**Expected flow:**
1. `GET /employee?firstName=Hilde&lastName=Johansen` — look up employee
2. `POST /travelExpense` with `employee: {id}`, `title`, `travelDetails: {departureDate: "2026-04-05", returnDate: "2026-04-07", isDayTrip: false, departureFrom: "Oslo", destination: "Bergen", departureTime: "07:00", returnTime: "19:00"}`, inline `mileageAllowances: [{rateType: {id: 743}, date: "2026-04-05", departureLocation: "Oslo", destination: "Bergen", km: 463, rate: 3.5, amount: 1620.5, isCompanyCar: false}]`, inline `perDiemCompensations: [{rateType: {id: 740}, count: 2, location: "Bergen", overnightAccommodation: "HOTEL"}]`

**Call count:** 2
**Note:** Both mileage and per diem can be inlined on the travel expense POST (verified against sandbox). Rate category IDs are hardcoded from known sandbox values.

---

### Task 5.3 — Invoice, Payment, and Credit Note (French)

**Prompt:**
> Créez un client "Lyon Conseil SARL", un produit "Audit Financier" à 8000 kr. Facturez 2 unités le 15 mars 2026, échéance le 15 avril 2026. Enregistrez le paiement intégral le 20 mars 2026. Puis créez une note de crédit datée du 25 mars 2026 avec le commentaire "Annulation de service".

**Expected flow:**
1. `POST /customer` — create "Lyon Conseil SARL"
2. `POST /product` — create "Audit Financier" with price 8000
3. `POST /invoice` — inline order (2 units, dates)
4. `GET /invoice/paymentType` — look up payment type
5. `PUT /invoice/{id}/:payment?paymentDate=2026-03-20&paymentTypeId=X&paidAmount=16000`
6. `PUT /invoice/{id}/:createCreditNote?date=2026-03-25&comment=Annulation de service`

**Call count:** 6 (assuming bank account already set)

---

### Task 5.4 — Travel Expense with Multiple Costs and Accommodation (English)

**Prompt:**
> Register a travel expense for employee "Sigrid Haugen" titled "Conference Stockholm". Travel from Oslo to Stockholm, departure April 14, 2026 at 06:00, return April 16, 2026 at 22:00. It's a foreign trip. Add: taxi cost 350 kr, flight cost 2800 kr, per diem for 2 overnight days abroad (hotel), and accommodation allowance for 2 nights.

**Expected flow:**
1. `GET /employee?firstName=Sigrid&lastName=Haugen` — look up employee
2. `GET /travelExpense/costCategory?count=50` — find taxi (32947605) and flight (32947590) categories
3. `GET /travelExpense/paymentType` — get payment type (32947574)
4. `POST /travelExpense` with `employee`, `title`, `travelDetails: {departureDate, returnDate, isDayTrip: false, isForeignTravel: true, departureFrom: "Oslo", destination: "Stockholm", departureTime: "06:00", returnTime: "22:00"}`, inline ALL sub-resources: `costs: [{taxi 350}, {flight 2800}]`, `perDiemCompensations: [{rateType: {id: 759}, count: 2, location: "Stockholm", overnightAccommodation: "HOTEL"}]`, `accommodationAllowances: [{rateType: {id: 754}, count: 2, location: "Stockholm"}]`

**Call count:** 4
**Note:** All 4 travel sub-resources (costs, mileage, per diem, accommodation) can be inlined in a single POST (verified against sandbox).

---

### Task 5.5 — Project Setup with Hourly Rates and Timesheet (German)

**Prompt:**
> Erstellen Sie ein Projekt "Digitalisierung Archiv" mit dem Mitarbeiter "Thomas Berg" als Teilnehmer. Erstellen Sie die Aktivität "Datenanalyse" und verknüpfen Sie sie mit dem Projekt. Registrieren Sie 6 Stunden Arbeit von Thomas Berg am 10. April 2026 auf diese Aktivität.

**Expected flow:**
1. `GET /token/session/>whoAmI` — admin employee ID for project manager
2. `GET /employee?firstName=Thomas&lastName=Berg` — look up employee
3. `POST /activity` — create "Datenanalyse" with `activityType: "PROJECT_GENERAL_ACTIVITY"`
4. `POST /project` — with `name`, `projectManager: {id: ADMIN_ID}`, `isInternal: true`, `startDate`, inline `participants: [{employee: {id: THOMAS_ID}}]`, inline `projectActivities: [{activity: {id: ACT_ID}}]`
5. `POST /timesheet/entry` — with `employee: {id: THOMAS_ID}`, `project: {id}`, `activity: {id: ACT_ID}`, `date: "2026-04-10"`, `hours: 6`

**Call count:** 5

---

### Task 5.6 — Employee Onboarding (Portuguese)

**Prompt:**
> Realize o onboarding completo do funcionário Ana Costa, nascida em 12/08/1995, email ana.costa@firma.no. Departamento "Finans". Data de início 1 de maio de 2026, tipo de emprego ordinário, forma permanente. Defina horário padrão de 7,5 horas por dia e tarifa horária de 550 kr.

**Expected flow:**
1. `GET /department?name=Finans` — look up department
2. `POST /employee` — with `firstName: "Ana"`, `lastName: "Costa"`, `dateOfBirth: "1995-08-12"`, `email`, `userType: "STANDARD"`, `department: {id}`, inline `employments: [{startDate: "2026-05-01", employmentDetails: [{date: "2026-05-01", employmentType: "ORDINARY", employmentForm: "PERMANENT"}]}]`
3. `POST /employee/standardTime` — with `employee: {id}`, `fromDate: "2026-05-01"`, `hoursPerDay: 7.5`
4. `POST /employee/hourlyCostAndRate` — with `employee: {id}`, `date: "2026-05-01"`, `rate: 550`

**Call count:** 4

---

### Task 5.7 — Travel with Mileage and Passenger Supplement (Norwegian Bokmål)

**Prompt:**
> Opprett en reiseregning for ansatt "Bjørn Nilsen" kalt "Prosjektbesøk Stavanger". Reise fra Oslo til Stavanger, avreise 20. april 2026, retur 20. april 2026 (dagsreise). Han kjørte egen bil 520 km med én passasjer.

**Expected flow:**
1. `GET /employee?firstName=Bjørn&lastName=Nilsen` — look up employee
2. `POST /travelExpense` — with `employee: {id}`, `title`, `travelDetails: {departureDate: "2026-04-20", returnDate: "2026-04-20", isDayTrip: true, departureFrom: "Oslo", destination: "Stavanger"}`, inline `mileageAllowances: [{rateType: {id: 743}, date: "2026-04-20", departureLocation: "Oslo", destination: "Stavanger", km: 520, rate: 3.5, amount: 1820, isCompanyCar: false}, {rateType: {id: 744}, date: "2026-04-20", departureLocation: "Oslo", destination: "Stavanger", km: 520, rate: 1.0, amount: 520, isCompanyCar: false}]`

**Call count:** 2
**Note:** Both main mileage and passenger supplement can be inlined as separate entries in the mileageAllowances array (verified against sandbox).

---

### Task 5.8 — Multi-product Invoice with Specific Quantities (Nynorsk)

**Prompt:**
> Lag ein faktura for kunden "Vestland Bygg AS" datert 1. april 2026, forfall 1. mai 2026. Legg til: 20 einingar "Betongblokk", 100 einingar "Armeringsjern 12mm", og 5 einingar "Sement 50kg". Kunden og alle produkta finst allereie.

**Expected flow:**
1. `GET /customer?customerName=Vestland Bygg AS` — look up customer
2. `GET /product?name=Betongblokk` — look up product 1
3. `GET /product?name=Armeringsjern 12mm` — look up product 2
4. `GET /product?name=Sement 50kg` — look up product 3
5. `POST /invoice` — with inline order, 3 orderLines referencing each product

**Call count:** 5 (assuming bank account already set)

---

### Task 5.9 — Payroll Voucher (English)

**Prompt:**
> Create a manual payroll journal entry dated March 31, 2026 with description "March salary — Ola Nordmann". Debit salary expense account 5000 for 45000 kr and credit salary payable account 2920 for 45000 kr.

**Expected flow:**
1. `GET /ledger/account?number=5000&count=5` — get salary expense account ID
2. `GET /ledger/account?number=2920&count=5` — get salary payable account ID
3. `POST /ledger/voucher` — with `date: "2026-03-31"`, `description`, `postings: [{account: 5000, vatType: {id: 0}, amountGross: 45000, amountGrossCurrency: 45000, row: 1}, {account: 2920, vatType: {id: 0}, amountGross: -45000, amountGrossCurrency: -45000, row: 2}]`

**Call count:** 3

---

### Task 5.10 — Full Customer and Invoice Pipeline (German)

**Prompt:**
> Erstellen Sie den Kunden "München Consulting GmbH" mit der Adresse Leopoldstraße 28, 80802 München. Erstellen Sie das Produkt "Strategieberatung" für 3500 kr. Erstellen Sie eine Rechnung vom 1. April 2026, fällig am 1. Mai 2026, mit 8 Einheiten des Produkts. Registrieren Sie die vollständige Zahlung am 15. April 2026.

**Expected flow:**
1. `POST /customer` — create with name and inline address
2. `POST /product` — create "Strategieberatung" with price 3500
3. `POST /invoice` — inline order (8 units, dates)
4. `GET /invoice/paymentType` — look up payment type
5. `PUT /invoice/{id}/:payment?paymentDate=2026-04-15&paymentTypeId=X&paidAmount=28000`

**Call count:** 5 (assuming bank account already set)

---

### Task 9.1 — Multi-line Invoice with Org# + Product# + Mixed VAT (Norwegian Bokmål)

**What's new:** Customer lookup by organizationNumber, product lookup by productNumber, multiple VAT types per invoice

**Prompt:**
> Opprett en faktura til kunden {name} (org.nr {org_nr}) med tre produktlinjer: {prod1} ({num1}) til 5400 kr med 25 % MVA, {prod2} ({num2}) til 6850 kr med 15 % MVA (næringsmiddel), og {prod3} ({num3}) til 13750 kr med 0 % MVA (avgiftsfri). Fakturadato 1. april 2026, forfall 1. mai 2026.

**Expected flow:**
1. `GET /customer?organizationNumber=X` — look up customer by org number
2. `GET /product?productNumber=N1&productNumber=N2&productNumber=N3` — batch look up all 3 products
3. `POST /invoice` — inline order with 3 orderLines, each with correct vatType ref (id=3 for 25%, id=31 for 15%, id=6 for 0%)

**Call count:** 3 (batch product lookup, VAT type IDs from skill docs, bank pre-set in setup)

---

### Task 10.1 — Fixed-price Project + Milestone Invoice (German)

**What's new:** Project update to fixed price, percentage-based milestone invoice

**Prompt:**
> Legen Sie einen Festpreis von 473250 NOK für das Projekt "{name}" fest. Stellen Sie dem Kunden 25 % des Festpreises als Meilensteinzahlung in Rechnung. Fakturadatum: 1. April 2026, Fälligkeitsdatum: 1. Mai 2026.

**Expected flow:**
1. `GET /project?name=X` — returns project with customer ID inline
2. `PUT /project/{id}` — set `isFixedPrice: true, fixedprice: 473250`
3. `POST /product` — milestone product at 118312.50 NOK (25% × 473250)
4. `POST /invoice` — inline order with project ref + customer from project response

**Call count:** 4

---

### Task 11.1 — Order → Invoice Conversion + Payment (German)

**What's new:** `PUT /order/{id}/:invoice` conversion of pre-existing order, payment on converted invoice

**Setup pre-creates:** Customer, 2 products (with prices), standalone order with 2 order lines

**Prompt:**
> Der Kunde {name} (Org.-Nr. {org_nr}) hat einen bestehenden Auftrag. Wandeln Sie diesen Auftrag in eine Rechnung um (Rechnungsdatum: 1. April 2026) und registrieren Sie die vollständige Zahlung am 1. April 2026.

**Expected flow:**
1. `GET /customer?organizationNumber=X` — look up customer by org number
2. `GET /order?customerId=X` — find the pre-created order
3. `PUT /order/{id}/:invoice?invoiceDate=2026-04-01` — converts order to invoice, returns invoice object
4. `GET /invoice/paymentType` — look up payment type ID
5. `PUT /invoice/{id}/:payment?paymentDate=2026-04-01&paymentTypeId=X&paidAmount={vatInclTotal}`

**Call count:** 5

**Verify checks:** customer exists, order is closed (isClosed=true after conversion), invoice exists, amountExcludingVat == 35650, amountOutstanding == 0

---

## Coverage Summary

### Entities covered:
| Entity | Create | Read/Lookup | Update | Delete |
|--------|--------|-------------|--------|--------|
| Employee | 1.1, 1.5, 1.8, 2.7, 5.6 | 2.3–2.5, 3.2, 3.5, 3.8, 5.2, 5.4, 5.5, 5.7 | 3.2 | — (not possible) |
| Customer | 1.2, 1.7, 2.2, 5.1, 5.3, 5.10 | 2.1, 2.3, 2.6, 3.1, 3.4, 3.6, 4.3, 4.5, 5.8 | 3.1, 3.4 | 4.3 |
| Product | 1.3, 2.2, 5.1, 5.3, 5.10 | 2.1, 2.6, 3.3, 4.4, 5.8 | 3.3 | 4.4 |
| Department | 1.4 | 1.1, 1.5, 1.8, 2.7, 3.7, 4.1, 5.6 | 3.7 | 4.1 |
| Invoice | 2.1, 2.2, 5.1, 5.3, 5.8, 5.10, 9.1, 10.1, 11.1 | 4.5 | — | — (use credit note) |
| Invoice Payment | 5.1, 5.3, 5.10, 11.1 | — | — | — |
| Credit Note | 5.3 | — | — | — |
| Order | 2.6, 11.1 | — | — | — |
| Order→Invoice | 11.1 | — | — | — |
| Project | 2.3, 2.5, 5.5, 10.1 | 3.6 | 3.6, 10.1 | 4.6 |
| Travel Expense | 2.4, 5.2, 5.4, 5.7 | 4.2 | — | 4.2 |
| Travel Cost | 2.4, 5.4 | — | — | — |
| Travel Mileage | 5.2, 5.7 | — | — | — |
| Travel Per Diem | 5.2, 5.4 | — | — | — |
| Travel Accommodation | 5.4 | — | — | — |
| Passenger Supplement | 5.7 | — | — | — |
| Activity | 1.6, 2.5, 5.5 | — | — | — |
| Timesheet | 2.5, 5.5 | — | — | — |
| Voucher | 2.8, 5.9 | 4.7 | — | — |
| Voucher Reverse | 4.7 | — | — | — |
| Employee Next of Kin | 2.7 | — | — | — |
| Employee Standard Time | 3.8, 5.6 | — | — | — |
| Employee Hourly Rate | 3.5, 5.6 | — | — | — |
| Employee Employment | 1.1, 1.8, 5.6 (inline) | — | — | — |
| Ledger Account | — | 2.1, 2.8, 5.1, 5.9 | (bank setup) | — |

### Languages covered:
- Norwegian Bokmål: 1.1, 2.2, 3.3, 4.2 (title in task — actual delete), 5.2, 5.7, 5.8
- English: 1.2, 1.8, 2.1, 2.3, 2.8, 3.2, 3.6, 4.3, 4.7, 5.4, 5.9
- German: 1.3, 3.4, 4.1, 5.5, 5.10
- Portuguese: 1.4, 2.6, 3.8, 4.6, 5.6
- Spanish: 1.7, 2.4, 3.5, 4.5, 5.1, 5.3
- French: 1.6, 3.1, 4.4, 2.5, 5.3
- Nynorsk: 1.5, 3.7, 5.8

### API flow patterns covered:
- **Pattern 1 (Create single):** 8 tasks (1.1–1.8)
- **Pattern 2 (Create with linking):** 8 tasks (2.1–2.8)
- **Pattern 3 (Modify existing):** 8 tasks (3.1–3.8)
- **Pattern 4 (Delete/reverse):** 7 tasks (4.1–4.7)
- **Pattern 5 (Multi-step):** 13 tasks (5.1–5.10, 9.1, 10.1, 11.1)

**Total: 44 tasks**
