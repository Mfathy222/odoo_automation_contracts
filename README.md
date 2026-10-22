# Zofirm Contract Management

Custom Contract Management module for **Odoo 19 Enterprise**.

`zofirm_contract` extends Odoo Sales, Sign, Approvals, Reporting, and Messaging to provide an integrated contract lifecycle starting from the quotation and continuing through contract generation, approval, signature, PDF generation, and contract tracking.

---

## Overview

The module provides centralized contract management inside Odoo and integrates contracts directly with Sales Quotations.

Instead of managing contracts as disconnected documents, the module links the contract lifecycle with:

- Sales Quotations
- Customers
- Contract Types
- Contract PDF Templates
- Payment Plans
- Project Schedules
- Odoo Sign
- Odoo Approvals
- Email
- Chatter & Activities
- Attachments
- Custom Financial Offers
- Multi-company environments

The primary contract model is:

```text
zofirm.contract
```

---

## Main Features

### 1. Contract Management

Provides a dedicated contract model:

```text
zofirm.contract
```

Contracts support:

- Automatic references
- Contract names
- Customer information
- Contract type
- Start and end dates
- Company assignment
- Quotation relationship
- PDF template selection
- Attachments
- Chatter
- Activities
- Signature tracking

The model inherits:

```python
mail.thread
mail.activity.mixin
```

allowing contract activity and communication to be tracked directly inside Odoo.

---

## 2. Sales Quotation Integration

Contracts are integrated directly with:

```text
sale.order
```

A contract can be created from an existing quotation, allowing commercial information to flow from the quotation into the contract.

This includes information such as:

- Customer
- Company
- Products / Services
- Contract scope
- Fees
- Payment schedule
- Project schedule
- Contract value
- Taxes
- Customer language

This keeps the quotation as the commercial source of the contract.

---

## 3. Contract Types

The module supports multiple contract/report types.

Examples currently implemented include:

### ERP Implementation Contract

Used for ERP/Odoo implementation projects.

The generated contract can include:

- Customer information
- Implementation scope
- Products and services
- Fees
- VAT
- Payment stages
- Terms and conditions

### ERP Maintenance Contract

A dedicated maintenance contract is available for:

```text
sijil_maintenance_contract
```

It supports maintenance, development, and technical support agreements for Odoo ERP systems.

The contract can contain:

- Contract duration
- Service activation date
- Monthly package amount
- VAT
- Monthly total
- Maintenance scope
- Development services
- Technical support

### Professional Engagement Contracts

The module also contains customized professional engagement/report templates, including accounting and professional-service engagements.

---

## 4. Dynamic Contract PDF Reports

Contracts are generated using Odoo QWeb PDF reports.

The system supports selecting different PDF templates depending on the contract type.

Example:

```text
ERP Implementation Contract
        ↓
Sijil Contract Report

ERP Maintenance Contract
        ↓
Sijil Maintenance Contract Report
```

The reports can dynamically retrieve information from:

```text
zofirm.contract
        ↓
sale.order
        ↓
res.partner
```

---

## 5. Arabic / RTL Contract Support

Contract reports include dedicated Arabic and RTL formatting.

Supported functionality includes:

- RTL document direction
- Arabic contract layouts
- Arabic section formatting
- Customer-specific information
- Arabic product/service descriptions
- Arabic contract duration
- Saudi Riyal formatting
- Customized headers and footers

The module contains specialized QWeb styling for professional Arabic contract output.

---

## 6. Customer Language Support

Products and services can be displayed according to the customer's configured language.

The system reads:

```python
partner.lang
```

and retrieves translated product names when generating contract content.

This allows the same quotation/product catalog to support multilingual contract generation.

---

## 7. Contract Scope from Quotation

Contract scope can be populated from quotation lines.

The module handles:

- Product lines
- Service lines
- Sections
- Product translations
- Product descriptions

Sections can also be resolved against products so that section names can be displayed using the customer's language.

---

## 8. Fees & Payment Schedule

The quotation contains a dedicated payment structure through:

```text
sale.order.fees.line
```

linked through:

```python
fees_payment_line_ids
```

This allows contract payment stages to be defined before the contract is generated.

The payment plan can then be rendered dynamically inside the contract PDF.

Typical information may include:

- Payment percentage
- Payment amount
- Due stage
- Payment description

---

## 9. Project Schedule

The module supports project schedule lines associated with quotations.

Model:

```text
sale.order.project.schedule.line
```

Schedule lines can contain:

- Description
- Duration
- Outputs

When a contract is created, project schedule information can be copied from the quotation to the corresponding contract.

---

## 10. Odoo Sign Integration

The module integrates contract documents with **Odoo Sign**.

Contracts can be connected to:

```text
sign.template
sign.request
sign.request.item
```

The contract PDF can be prepared as a Sign template and used to create signature requests.

The integration maintains relationships between:

```text
Contract
   ↓
Sign Template
   ↓
Sign Request
   ↓
Signer(s)
```

---

## 11. Automatic Sign Defaults

When sending a contract for signature, the module can automatically prepare information such as:

- Contract reference
- Signature subject
- PDF filename
- Validity date
- Customer
- Signer
- Attachments
- Email configuration

Example subject:

```text
Signature Request – <Contract Name>
```

The generated contract PDF can also be automatically attached to the signature process.

---

## 12. Signature Status Synchronization

The module tracks signature progress and synchronizes it with the contract.

When a Sign request reaches states such as:

```text
signed
completed
```

the corresponding contract can be updated automatically.

This allows users to see contract signature status without manually checking Sign requests.

---

## 13. Signed Document Tracking

Contracts can display related signed requests.

The module can detect:

- Partially signed requests
- Fully signed requests
- Completed signature requests

Smart actions can be used to navigate from the contract to the corresponding signature records.

---

## 14. Approval Workflow

The module adds an approval layer before certain contract actions.

It extends:

```text
approval.request
```

with contract-specific information.

Supported contract actions include:

```text
mail_send
sign_send_request
sign_completed_document
```

This allows sensitive contract communication to be controlled through Odoo Approvals.

---

## 15. User vs Administrator Workflow

The contract sending workflow distinguishes between normal users and administrators.

### Normal User

When a normal user attempts a controlled contract action:

```text
User
 ↓
Request Action
 ↓
Approval Request
 ↓
Approver
 ↓
Approve / Reject
 ↓
Execute Original Action
```

### Administrator

Authorized administrators can execute supported actions directly without requiring the same approval process.

This provides operational control while maintaining a practical workflow for administrators.

---

## 16. Configurable Contract Approvers

Contract approvers can be configured at company level.

Configuration is designed around:

```text
Settings
   ↓
Sijil Email
   ↓
Contract Approval
```

The configured users become responsible for reviewing contract actions.

The module validates that:

- Approvers exist
- Approvers are active
- Approvers have access to the relevant company

---

## 17. Approval PDF Attachment

When an approval request is generated, the module can generate the actual contract PDF and attach it directly to the approval request.

This allows the approver to review the document being approved instead of approving only a generic system action.

Conceptually:

```text
Contract
   ↓
Generate PDF
   ↓
Approval Request
   ↓
Contract PDF Attachment
```

---

## 18. Approval Payload Preservation

For actions involving Odoo Sign, the module preserves the information entered by the original user before approval.

This may include:

- Sign template
- Subject
- Filename
- Validity
- Message
- Reference
- Signing order
- Signers
- Roles
- SMS numbers
- Authentication methods
- Attachments
- CC partners

After approval, the stored action can be executed using the original user selections.

---

## 19. Contract Attachments

Generated contract PDFs can be stored as Odoo attachments:

```text
ir.attachment
```

Attachments can be linked to:

- Contracts
- Approval Requests
- Sign Templates

This provides traceability throughout the contract lifecycle.

---

## 20. Chatter Integration

Contracts support Odoo Chatter.

Important events can therefore be recorded directly against the contract, including:

- Contract creation
- Generated PDFs
- Project schedule copying
- Signature activity
- Approval activity
- Errors
- Attachments

This creates an auditable history for each contract.

---

## 21. Financial Offer Reports

The module extends Odoo reporting to support customized financial offers.

Custom report handling includes financial offer variants and integration with Odoo quotation documents.

The reporting engine can combine:

```text
Header PDFs
     ↓
Product PDFs
     ↓
Custom Financial Offer
     ↓
Footer PDFs
```

into a single final PDF.

---

## 22. Quote Builder PDF Integration

The module extends:

```text
ir.actions.report
```

to integrate custom financial reports with quotation documents.

Supported documents may include:

- Header documents
- Product-related PDFs
- Financial quotation
- Footer documents

The final result is assembled into one PDF document.

---

## 23. Custom Report Redirection

The module can redirect Odoo's standard quotation PDF generation to custom financial reports depending on the company.

This allows different companies in the same Odoo database to use different quotation/reporting behavior.

---

## 24. Multi-Company Support

The module includes company-aware logic.

A configured SIJIL company constant is used in several workflows:

```python
SIJIL_COMPANY_ID = 2
```

Company-specific logic controls selected:

- Contract behavior
- Reports
- Buttons
- Approval users
- Email configuration
- Financial offer behavior

> Important: The company ID is currently configuration-dependent. When installing the module on another database, verify company IDs before production use.

---

## 25. Contract Naming

Contract names can be generated dynamically from the customer and contract type.

Examples:

```text
عقد شركة <Customer>
```

and for maintenance:

```text
عقد صيانة شركة <Customer>
```

This provides more meaningful contract identification than relying only on technical sequence numbers.

---

## 26. Audit / Reference Validation

The module contains validation for selected contract reference fields.

For example, duplicate audit/reference numbers can be prevented using Odoo constraints.

This protects contract records from accidental duplicate identifiers.

---

## 27. Contract Duration

The module includes logic to calculate human-readable Arabic contract durations.

The calculation supports:

- Years
- Months
- Days

Example output:

```text
سنة واحدة و3 أشهر و5 أيام
```

This can be rendered directly inside contract documents.

---

## 28. Technical Architecture

Main extended/custom models include:

```text
zofirm.contract
sale.order
sale.order.project.schedule.line
zofirm.contract.schedule.line
approval.request
sign.template
sign.send.request
sign.request
sign.request.item
ir.actions.report
ir.actions.actions
```

---

## 29. Core Workflow

The overall workflow can be represented as:

```text
Customer
   ↓
Quotation
   ↓
Products / Services
   ↓
Scope of Work
   ↓
Fees & Payment Schedule
   ↓
Project Schedule
   ↓
Create Contract
   ↓
Select Contract Type / PDF Template
   ↓
Generate Contract PDF
   ↓
Approval (when required)
   ↓
Odoo Sign
   ↓
Customer Signature
   ↓
Signature Status Sync
   ↓
Signed Contract
   ↓
Attachments / Chatter / Tracking
```

---

## 30. Approval & Signature Workflow

```text
Employee
   ↓
Generate Contract
   ↓
Prepare Sign Template
   ↓
Configure Signers
   ↓
Send Request
   ↓
Approval Required?
   ├── No → Send Directly
   │
   └── Yes
        ↓
   Create Approval Request
        ↓
   Attach Contract PDF
        ↓
   Approver Reviews
        ↓
   Approve / Reject
        ↓
   Execute Original Sign Action
        ↓
   Customer Signs
        ↓
   Contract Status Updated
```

---

## Dependencies

The module relies on Odoo applications/features including functionality from:

```text
base
mail
sale
sale_management
approvals
sign
```

Additional dependencies may exist depending on the complete module manifest and installed localization/custom modules.

---

## Installation

1. Copy the module into the Odoo custom addons directory.

```bash
custom_addons/zofirm_contract
```

2. Restart the Odoo server.

3. Update the Apps List.

4. Search for the contract module.

5. Install or upgrade the module.

For command-line upgrade:

```bash
./odoo-bin -d <database_name> -u zofirm_contract
```

For Docker-based environments, use the equivalent Odoo container upgrade command.

---

## Configuration

After installation, verify:

### Company

Confirm that company-specific IDs correspond to the intended companies.

Example:

```python
SIJIL_COMPANY_ID = 2
```

### Contract Approvers

Configure authorized users from the relevant company settings.

### Email

Configure the outgoing email/mail server used for contract communication.

### Odoo Sign

Verify:

- Sign roles
- Signers
- Sign templates
- Signature access
- Sign email settings

### PDF Templates

Verify that all required QWeb reports and PDF templates are installed and accessible.

---

## Security Considerations

Because this module controls contractual documents and signature requests, production deployments should verify:

- Contract access rights
- Approval permissions
- Administrator permissions
- Multi-company record rules
- Sign permissions
- Attachment permissions
- Customer information access
- Email server permissions

Do not rely only on UI visibility for security-sensitive operations.

---

## Important Technical Notes

### Company IDs

Some functionality currently relies on fixed company IDs.

Before migrating the module to another database, review all occurrences of:

```python
SIJIL_COMPANY_ID
```

and other direct company-ID comparisons.

### Report Templates

QWeb reports contain company-specific contractual wording and layouts.

Review the legal wording before deploying the reports for another legal entity.

### Odoo Sign

Some Sign functionality depends on Odoo Enterprise internals and may require verification after an Odoo version upgrade.

### Custom Reports

The module overrides parts of Odoo's PDF rendering workflow. Report behavior should therefore be regression-tested after Odoo upgrades.

---

## Recommended Testing

Before production deployment, test at minimum:

1. Create quotation.
2. Add products/services.
3. Add scope of work.
4. Configure payment stages.
5. Configure project schedule.
6. Create contract.
7. Select contract type.
8. Generate PDF.
9. Verify Arabic/RTL output.
10. Verify customer/product translations.
11. Generate Sign template.
12. Configure signers.
13. Submit as normal user.
14. Verify Approval Request.
15. Verify PDF attachment in Approval.
16. Approve request.
17. Verify Sign request is sent.
18. Complete signature.
19. Verify contract signature status.
20. Verify signed document tracking.
21. Verify Chatter entries.
22. Repeat using administrator account.
23. Repeat using another company.

---

## Suggested Module Structure

```text
zofirm_contract/
│
├── __init__.py
├── __manifest__.py
│
├── models/
│   ├── __init__.py
│   ├── zofirm_contract.py
│   ├── sale_order.py
│   ├── ir_actions_report.py
│   ├── contract_approval_request.py
│   ├── sign_request.py
│   └── sign_template.py
│
├── views/
│   ├── contract_views.xml
│   ├── sale_order_views.xml
│   ├── approval_views.xml
│   └── settings_views.xml
│
├── report/
│   ├── contract_report.xml
│   ├── sijil_contract.xml
│   ├── maintenance_contract.xml
│   ├── bookkeeping_contract.xml
│   ├── financial_offer.xml
│   └── report_actions.xml
│
├── security/
│   ├── ir.model.access.csv
│   └── security.xml
│
├── data/
│   └── sequences.xml
│
├── static/
│   └── img/
│       └── sijilacc_logo.png
│
└── README.md
```

> The structure above is a documentation-oriented representation. Verify exact filenames against the deployed module before using it as a release manifest.

---

## Business Value

`zofirm_contract` transforms the standard quotation-to-contract process into an integrated Odoo workflow.

Instead of separately managing:

```text
Quotation
PDF
Approval
Email
Signature
Signed Document
```

the module connects these activities into a traceable process:

```text
Quotation
   ↓
Contract
   ↓
Approval
   ↓
Signature
   ↓
Signed Contract
```

This reduces manual document handling and keeps commercial, contractual, approval, and signature information connected inside Odoo.

---

## Technology

Developed using:

- Python
- Odoo ORM
- XML
- QWeb
- Odoo Reports
- Odoo Sales
- Odoo Approvals
- Odoo Sign
- Odoo Mail / Chatter
- PDF processing
- RTL / Arabic report customization

---

## Compatibility

```text
Odoo 19 Enterprise
```

The module contains integrations with Enterprise applications such as Odoo Sign and Approvals.

---

## Developer

Custom Odoo development for contract lifecycle automation, quotation integration, approval control, document generation, and electronic signature workflows.

---

## License

Internal / Proprietary Module.

Distribution, modification, or deployment outside the authorized environment should follow the organization's applicable licensing and source-code policies.#   z o f i r m _ c o n t r a c t  
 