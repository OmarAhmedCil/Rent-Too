# Contract Management Tool — End User Guide

**Last Updated:** April 2026

---

## Table of Contents
1. [Getting Started](#getting-started)
2. [Logging In](#logging-in)
3. [Dashboard](#dashboard)
4. [Managing Contracts](#managing-contracts)
5. [Master Data (Lessors, Assets, Stores, Services)](#master-data)
6. [Distribution](#distribution)
7. [Payments](#payments)
8. [Download Data](#download-data)
9. [Bulk Import](#bulk-import)
10. [Email Notifications](#email-notifications)
11. [Users & Roles](#users--roles)
12. [Action Logs](#action-logs)
13. [Troubleshooting](#troubleshooting)

---

## Getting Started

The Contract Management Tool is a web application for managing lease contracts, tracking payments, and generating reports.

**Requirements:** A modern web browser (Chrome, Edge, Firefox, Safari). Your administrator will give you a login and the appropriate permissions.

---

## Logging In

1. Open the application URL in your browser.
2. Enter your **email address** and **password**.
3. Click **Login**.

> **First-time setup:** The default admin account is `admin@contracttool.com` / `admin123`. Change this password immediately after first login.

To log out, click **Logout** in the top-right corner of the sidebar.

---

## Dashboard

The Dashboard shows a quick summary:
- Counts for contracts (including by type), lessors, assets, stores, and services
- **Due Amounts** — EGP and USD totals from distribution **due** (upcoming from the start of this month, this month, and this year)
- Quick-action buttons to navigate to common pages

---

## Managing Contracts

Navigate to **📄 Contracts → Contract Management**.

### Create a Contract
1. Click **+ New Contract**.
2. Fill in:
   - **Contract Name** (required)
   - **Currency** (EGP / USD)
   - **Commencement Date** and **Tenure** (years + months)
   - **Asset / Store** — choose Store or Other, then select the specific item
   - **Contract Type** — Fixed, Revenue Share (Store only), or ROU
3. Add **Lessors**: select a lessor, enter their share %. Total shares must equal 100%.
4. Add **Services** (optional): select service, enter amount and yearly increase %.
5. Fill in payment settings:
   - **First Payment Date**, **Payment Frequency** (Monthly / Quarter / Yearly)
   - **Tax %**, **Yearly Increase %**
   - **Rent Amount** (Fixed / ROU)
   - **Free Months** / **Advance Months** (comma-separated period numbers, e.g. `1,2`)
   - Revenue Share fields (if applicable)
6. Click **Save Contract**.

### Edit a Contract
1. In Contract Management, click **Edit** on the row.
2. Modify fields, lessors, or services.
3. Click **Update Contract**.

### Delete a Contract
1. In Contract Management, click **Delete** on the row.
2. Confirm by typing **DELETE**.

> Deleting a contract removes all related distribution and payment records.

---

## Master Data

### Lessors (👥)
Lessors are landlords / vendors who receive payments.

- **Create**: Name (required), description, tax ID, supplier code, IBAN
- **Edit**: Update any field including IBAN
- **Withholding Exemption**: In the lessor edit page, you can add date ranges during which withholding tax is **not** deducted from that lessor's payments.

### Assets (🏢) & Stores
- **Assets**: Non-store locations (name + cost center)
- **Stores**: Store locations used for Revenue Share contracts
- Both support Create / Edit / Delete

### Services (🛠️)
Services are additional charges on top of rent.
- Each service has a name, description, and **currency** (EGP or USD)
- A service's currency is inherited by all contracts that include it

---

## Distribution

Navigate to **📊 Distribution → Contracts Distribution**.

Distribution calculates each lessor's monthly share of rent for each contract. The system stores **one summary row per month per contract** and keeps per-lessor detail inside that row; the Payment Center still lists amounts **per lessor** for editing and payment runs.

### Generate Distribution
1. Find the contract in the list.
2. Click **Generate**.
3. The system calculates all monthly rows based on the contract dates, rent, and lessor shares.

### Regenerate Distribution
Click **Regenerate** to recalculate. Do this after changing a contract or updating revenue data.

### Edit Distribution
Click **Edit** on a specific distribution row to adjust individual values.

### Delete Distribution
Click **Delete** to remove all distribution rows for a contract.

> After generating distribution, payment records are created automatically.

---

## Payments

Navigate to **💳 Payments → Payment Center**.

This page lists all contracts. For each contract you can view and edit the payment distribution.

### Edit Payments (Discount & Advance)
1. Find the contract, click **Edit**.
2. An inline table shows each distribution row:

   | Date | Lessor | Rent Amount | **Discount** | **Advance** | Lessor Due |
   |---|---|---|---|---|---|
   | read-only | read-only | read-only | ✏️ editable | ✏️ editable | read-only |

3. Enter discount or advance amounts. The combined total per row **cannot exceed the rent amount** — a 🔴 indicator appears if it does.
4. Click **Save Edited Payments**.
5. On save, the system recalculates lessor due amount, tax, and withholding, then returns you to Payment Center.

> **Note:** Discount and advance editing is available for **Fixed** and **ROU** contracts only. Revenue Share contracts are read-only in this view.

---

## Download Data

Navigate to **📤 Download Data**.

1. Choose what to export: Contracts, Distribution, Payments, Services, Revenue Share data.
2. Apply filters (contract, date range, type).
3. Click **Download** to get an Excel or CSV file.

---

## Bulk Import

Navigate to **📥 Bulk Import**.

1. Click **Download Template** to get the Excel import template (contracts sheet includes optional **Advance Payment (Fixed)** and **Revenue Share Payment Advance**, and yearly increase fields aligned with **Create Contract**).
2. Fill in the template with contract data.
3. Upload the completed file and click **Import**.
4. Review any validation errors shown after import.

---

## Email Notifications

Navigate to **📧 Email Notifications**.

### Weekly Payment Emails
Set up automatic weekly emails with a **CSV attachment** of payment lines for the calendar week:
- Choose **Day of Week** and **Send Time**
- Enter **Recipient** email addresses
- Select which contracts to include (All / Selected / Filtered by type)

### Payment Reminders
Reminders are based on **`payment_date`**: each send includes payment rows whose dates fall in the **next N days** (you choose **N**), with the same contract scope options as weekly emails.
- The email has a short summary (totals and unique counts **from that attachment only**) plus the **CSV**; details are in the file, not as a long list in the email body.
- You can send a test reminder from the configuration screen.

---

## Users & Roles

### Users (👤)
Manage who can log in:
- **Create User**: email, name, password (min 6 chars), active status
- **Edit User**: change name, email, active status, or password
- **Delete User**: type DELETE to confirm. You cannot delete your own account.

### Roles & Permissions (🔐)
Roles group permissions together. Users are assigned roles.

- **Manage Roles**: create / edit / delete roles
- **Assign Permissions to Roles**: check permissions per module for each role
- **Assign Roles to Users**: give a user one or more roles

**Permission modules**: Contracts, Lessors, Assets, Stores, Services, Distribution, Payments, Download, Bulk Import, Users, Roles, Logs, Email, Admin

---

## Action Logs

Navigate to **📋 Action Logs**.

View a full audit trail of every action (create, edit, delete, generate, login, export, bulk import) with:
- Who performed it and when
- What entity was affected
- IP address

Filter by action type, entity type, user, or date range. Export to CSV.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Can't see a page or button | You may not have the required permission — ask your admin |
| Distribution didn't generate | Verify the contract has lessors and valid dates; check for revenue data if Revenue Share |
| Payments not appearing after generating distribution | Try Regenerate Distribution |
| Discount/advance fields greyed out in Edit Payment | Contract type is Revenue Share — not supported |
| 🔴 appears in Edit Payment row | Discount + advance total exceeds the rent amount for that row — reduce the values |
| Login fails | Check email / password; account may be inactive — ask admin |
| Bulk import errors | Download a fresh template; check column headers and date formats |
