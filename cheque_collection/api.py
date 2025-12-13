from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
import frappe
from frappe import _

@frappe.whitelist()
def create_journal_entry(payment_entry_name: str, bank_account: str, posting_date: str = None) -> str:
    """
    Create a Journal Entry to move funds from the PDC account to the selected Bank account for a 'Pay' Payment Entry.

    - Debit: Account mapped to the Mode of Payment on the Payment Entry (e.g., PDC account)
    - Credit: Selected Bank Account

    Returns the created Journal Entry name.
    """
    if not payment_entry_name:
        frappe.throw("Missing Payment Entry name")

    if not bank_account:
        frappe.throw("Please select a Bank account")
    
    if not posting_date:
        frappe.throw("Please select a Posting date")

    doc = frappe.get_doc("Payment Entry", payment_entry_name)

    if doc.docstatus != 1:
        frappe.throw("Payment Entry must be submitted before creating Journal Entry")

    if doc.payment_type != "Pay":
        frappe.throw("This action is only for 'Pay' type Payment Entries.")

    # Avoid duplicate creation if an active JE is already linked
    if getattr(doc, "custom_journal_entry", None):
        existing_status = frappe.db.get_value("Journal Entry", doc.custom_journal_entry, "docstatus")
        if existing_status is None:
            # stale link -> clear
            frappe.db.set_value("Payment Entry", doc.name, "custom_journal_entry", None)
        elif int(existing_status) != 2:
            frappe.throw(_("A Journal Entry is already linked: {0}. Please return/cancel it before creating a new one.").format(doc.custom_journal_entry))

    # Validate selected bank account
    bank_acc = frappe.db.get_value(
        "Account",
        bank_account,
        ["account_type", "company", "is_group"],
        as_dict=True,
    )

    if not bank_acc:
        frappe.throw("Selected Bank account not found")
    if bank_acc.company != doc.company:
        frappe.throw("Selected Bank account must belong to the same company as the Payment Entry")

    # Determine the PDC (debit) account using Mode of Payment mapping
    if not doc.mode_of_payment:
        frappe.throw("Mode of Payment is required on the Payment Entry to determine the PDC account")

    mop_acc = get_bank_cash_account(doc.mode_of_payment, doc.company)
    debit_account = (mop_acc or {}).get("account")

    if not debit_account:
        frappe.throw("Could not determine the PDC account from the Mode of Payment mapping")

    if debit_account == bank_account:
        frappe.throw("Bank account and PDC account cannot be the same")

    # Amount to move
    amount = float(doc.paid_amount or 0)
    if amount <= 0:
        frappe.throw("Paid amount must be greater than zero")

    # Create Journal Entry
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Bank Entry"
    je.company = doc.company
    je.posting_date = posting_date
    je.cheque_no = doc.reference_no
    je.cheque_date = doc.reference_date
    je.user_remark = _("PDC to Bank for Payment Entry {0}").format(doc.name)

    # Debit: PDC Account (from Mode of Payment mapping)
    je.append(
        "accounts",
        {
            "account": debit_account,
            "debit_in_account_currency": amount,
        },
    )

    # Credit: Selected Bank Account
    je.append(
        "accounts",
        {
            "account": bank_account,
            "credit_in_account_currency": amount,
        },
    )

    je.insert()
    je.submit()

    # Link back on the Payment Entry
    frappe.db.set_value("Payment Entry", doc.name, "custom_journal_entry", je.name)
    
    # Set custom_deposit to Yes
    frappe.db.set_value("Payment Entry", doc.name, "custom_deposit", "Yes")
    
    frappe.db.commit()
    return je.name


@frappe.whitelist()
def cancel_journal_entry(payment_entry_name: str) -> str:
    """Create a reverse Journal Entry to undo the original PDC to Bank movement.

    Returns the reverse Journal Entry name created.
    """
    if not payment_entry_name:
        frappe.throw("Missing Payment Entry name")

    doc = frappe.get_doc("Payment Entry", payment_entry_name)

    if doc.docstatus != 1:
        frappe.throw("Payment Entry must be submitted to perform return action")

    if not getattr(doc, "custom_journal_entry", None):
        frappe.throw("No Journal Entry is linked to this Payment Entry")

    je_name = doc.custom_journal_entry
    original_je = frappe.get_doc("Journal Entry", je_name)

    if original_je.docstatus != 1:
        frappe.throw(_("The linked Journal Entry {0} is not submitted. Cannot create reverse entry.").format(je_name))

    # Create reverse Journal Entry
    reverse_je = frappe.new_doc("Journal Entry")
    reverse_je.voucher_type = "Bank Entry"
    reverse_je.company = original_je.company
    reverse_je.posting_date = frappe.utils.today()
    reverse_je.cheque_no = doc.reference_no
    reverse_je.cheque_date = doc.reference_date
    reverse_je.user_remark = _("Reverse Entry for Payment Entry Return {0} - Original JE: {1}").format(doc.name, je_name)

    # Reverse the accounts - swap debit and credit
    for account_row in original_je.accounts:
        reverse_je.append(
            "accounts",
            {
                "account": account_row.account,
                "debit_in_account_currency": account_row.credit_in_account_currency or 0,
                "credit_in_account_currency": account_row.debit_in_account_currency or 0,
            },
        )

    reverse_je.insert()
    reverse_je.submit()

    # Clear the custom_journal_entry link on Payment Entry (original JE remains in system)
    frappe.db.set_value("Payment Entry", doc.name, "custom_journal_entry", None)
    
    # Set custom_deposit to No
    frappe.db.set_value("Payment Entry", doc.name, "custom_deposit", "No")
    
    frappe.db.commit()
    
    frappe.msgprint(_("Reverse Journal Entry {0} created successfully. Original JE {1} remains in the system.").format(reverse_je.name, je_name))
    
    return reverse_je.name
