# Copyright (c) 2025, xcode and contributors
# For license information, please see license.txt

from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from erpnext.accounts.doctype.payment_entry.payment_entry import get_party_details
import frappe
from frappe.model.document import Document
from frappe import _

class PDCCheque(Document):

    def validate(self):
        # Validate duplicate parties in the references table
        self.validate_duplicate_parties()

        # Validate if any invoices have customers that are not in the references
        self.validate_invoices_parties()

        # Validate total paid amount in invoices
        self.validate_total_paid_amount()

    def validate_duplicate_parties(self):
        """Ensure no duplicate parties in the references table."""
        party_set = set()
        for reference in self.references:
            if reference.party in party_set:
                frappe.throw(f"Party {reference.party} is already added. Please avoid duplicates.")
            party_set.add(reference.party)

    def validate_invoices_parties(self):
        """Ensure all invoices belong to valid customers in the references table."""
        party_set = {reference.party for reference in self.references}
        invoices_to_remove = []
        for invoice in self.invoices:
            if invoice.customer not in party_set:
                invoices_to_remove.append(invoice.name)

        # Remove invoices with invalid customers and notify the user
        if invoices_to_remove:
            for invoice_name in invoices_to_remove:
                self.remove_invoice(invoice_name)
            
    def validate_total_paid_amount(self):
        """Ensure total paid amount in invoices does not exceed the allocated amount."""
        total_paid_amount = sum([invoice.paid_amount for invoice in self.invoices if invoice.paid_amount])

        if total_paid_amount > self.amount:
            frappe.throw(
                _("The total paid amount ({0}) exceeds the allocated amount ({1}). Please adjust the payments.").format(
                    frappe.format_value(total_paid_amount, "Currency"),
                    frappe.format_value(self.amount, "Currency")
                )
            )
        elif total_paid_amount < self.amount:
            frappe.throw(
                _("The total paid amount ({0}) is less than the allocated amount ({1}). Please adjust the payments.").format(
                    frappe.format_value(total_paid_amount, "Currency"),
                    frappe.format_value(self.amount, "Currency")
                )
            )

    def remove_invoice(self, invoice_name):
        """Helper function to remove an invoice by name."""
        self.invoices = [invoice for invoice in self.invoices if invoice.name != invoice_name]

    def on_submit(self):
        """Create single Payment Entry for each customer, with multiple invoice references."""
        customer_invoices_map = self.get_customer_invoices_map()

        # Iterate over each customer and create a single Payment Entry for multiple invoices
        for customer, invoices in customer_invoices_map.items():
            self.create_payment_entry_for_customer(customer, invoices)

    def get_customer_invoices_map(self):
        """Create a mapping of customers to their respective invoices."""
        customer_invoices_map = {}
        
        for row in self.get("invoices"):
            if row.paid_amount and row.paid_amount > 0:
                if row.customer:
                    if row.customer not in customer_invoices_map:
                        customer_invoices_map[row.customer] = []
                    customer_invoices_map[row.customer].append(row)
                else:
                   continue

        return customer_invoices_map

    def create_payment_entry_for_customer(self, customer, invoices):
        if not invoices:
            return

        # Calculate the total paid amount for the specific customer
        paid_amount = sum([invoice.paid_amount for invoice in invoices if invoice.customer == customer])

        if paid_amount == 0:
            frappe.throw(_("No valid paid amounts found for customer {0}").format(customer))

        # Get the posting date from the corresponding reference table row (assuming it is the same for all)
        reference_row = next((row for row in self.references if row.party == customer), None)
        if not reference_row:
            frappe.throw(_("Could not find reference data for customer {0}").format(customer))
        remark = reference_row.remarks
        

        # Get party account details
        party_type = "Customer"
        party_details = get_party_details(self.company, party_type, customer, self.posting_date)

        # Fetch the company bank or cash account (paid_to)
        bank = get_bank_cash_account(self.mode_of_payment, self.company)

        if not bank:
            frappe.throw(_("Please define a default bank or cash account for the company."))
        
        
        # Create the payment entry
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.company = self.company
        pe.party_type = party_type
        pe.party = customer
        pe.posting_date = self.posting_date
        pe.mode_of_payment = self.mode_of_payment
        pe.paid_amount = paid_amount
        pe.received_amount = paid_amount
        pe.paid_from = party_details['party_account']
        pe.party_balance = party_details['party_balance']
        pe.account_balance = party_details['account_balance']
        pe.party_bank_account = party_details["party_bank_account"]
        pe.paid_to = bank['account']
        pe.bank_account =party_details["bank_account"]
        pe.reference_no = str(self.reference_no + " \ " + self.employee_name)
        pe.reference_date = self.reference_date
        pe.custom_employee = self.employee
        pe.custom_employee_name = self.employee_name
        pe.custom_remark = remark
        

        # Add invoice references
        for invoice in invoices:
            allocated_amount = min(invoice.paid_amount, invoice.outstanding_amount)
            pe.append("references", {
                "reference_doctype": invoice.reference_type,
                "reference_name": invoice.reference_name,
                "total_amount": invoice.grand_total,
                "outstanding_amount": invoice.outstanding_amount,
                "allocated_amount": allocated_amount
            })

        # Insert and submit the Payment Entry
        pe.insert()
        pe.submit()

        frappe.msgprint(
            _("Payment Entry created for Customer {0} with total Paid Amount {1}").format(
                customer,
                frappe.format_value(paid_amount, "Currency")
            )
        )


    def get_reference_row_for_customer(self, customer):
        """Fetch the reference row from the Multi Payment Entry Reference table for the given customer."""
        for row in self.get("references"):
            if row.party == customer:
                return row
        return None


@frappe.whitelist()
def create_journal_entry(pdc_cheque_name: str, bank_account: str) -> str:
    """
    Create a Journal Entry to move funds from the PDC account to the selected Bank account.

    - Debit: Selected Bank Account
    - Credit: Account mapped to the Mode of Payment on the PDC Cheque (e.g., PDC account)

    Returns the created Journal Entry name.
    """
    if not pdc_cheque_name:
        frappe.throw("Missing PDC Cheque name")

    if not bank_account:
        frappe.throw("Please select a Bank account")

    doc = frappe.get_doc("PDC Cheque", pdc_cheque_name)

    if doc.docstatus != 1:
        frappe.throw("PDC Cheque must be submitted before creating Journal Entry")

    # Avoid duplicate creation if an active JE is already linked
    if getattr(doc, "journal_entry", None):
        existing_status = frappe.db.get_value("Journal Entry", doc.journal_entry, "docstatus")
        if existing_status is None:
            # stale link -> clear
            frappe.db.set_value("PDC Cheque", doc.name, "journal_entry", None)
        elif int(existing_status) != 2:
            frappe.throw(_("A Journal Entry is already linked: {0}. Please return/cancel it before creating a new one.").format(doc.journal_entry))

    # Validate selected bank account
    bank_acc = frappe.db.get_value(
        "Account",
        bank_account,
        ["account_type", "company", "is_group", "account_currency"],
        as_dict=True,
    )

    if not bank_acc:
        frappe.throw("Selected Bank account not found")

    if bank_acc.account_type != "Bank":
        frappe.throw("Selected account is not of type 'Bank'")

    if bank_acc.is_group:
        frappe.throw("Selected account cannot be a group account")

    if bank_acc.company != doc.company:
        frappe.throw("Selected Bank account must belong to the same company as the PDC Cheque")

    # Determine the PDC (credit) account using Mode of Payment mapping
    if not doc.mode_of_payment:
        frappe.throw("Mode of Payment is required on the PDC Cheque to determine the PDC account")

    mop_acc = get_bank_cash_account(doc.mode_of_payment, doc.company)
    credit_account = (mop_acc or {}).get("account")

    if not credit_account:
        frappe.throw("Could not determine the PDC account from the Mode of Payment mapping")

    if credit_account == bank_account:
        frappe.throw("Bank account and PDC account cannot be the same")

    # Amount to move
    amount = float(doc.amount or 0)
    if amount <= 0:
        frappe.throw("PDC Cheque amount must be greater than zero")
    # print('////////////////////////////////////////////////////')
    # print(doc.reference_no)
    # print(getattr(doc, "reference_no", None))
    # Create Journal Entry
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Bank Entry"
    je.company = doc.company
    je.posting_date = doc.posting_date or frappe.utils.nowdate()
    # Reference details are mandatory for Bank Entry
    je.cheque_no = getattr(doc, "reference_no", None)
    je.cheque_date = getattr(doc, "reference_date", None)
    je.user_remark = _("PDC to Bank for {0}").format(doc.name)

    # Debit: Selected Bank Account
    je.append(
        "accounts",
        {
            "account": bank_account,
            "debit_in_account_currency": amount,
        },
    )

    # Credit: PDC Account (from Mode of Payment mapping)
    je.append(
        "accounts",
        {
            "account": credit_account,
            "credit_in_account_currency": amount,
        },
    )

    je.insert()
    je.submit()

    # Link back on the PDC Cheque
    frappe.db.set_value("PDC Cheque", doc.name, "journal_entry", je.name)

    return je.name


@frappe.whitelist()
def cancel_journal_entry(pdc_cheque_name: str) -> str:
    """Cancel the Journal Entry linked to this PDC Cheque and clear the link.

    Returns the Journal Entry name affected.
    """
    if not pdc_cheque_name:
        frappe.throw("Missing PDC Cheque name")

    doc = frappe.get_doc("PDC Cheque", pdc_cheque_name)

    if doc.docstatus != 1:
        frappe.throw("PDC Cheque must be submitted to perform return action")

    if not getattr(doc, "journal_entry", None):
        frappe.throw("No Journal Entry is linked to this PDC Cheque")

    je_name = doc.journal_entry
    je = frappe.get_doc("Journal Entry", je_name)

    if je.docstatus == 1:
        je.cancel()
    elif je.docstatus == 0:
        je.delete()
    # if already cancelled (2) -> nothing to do

    # Clear link on PDC Cheque
    frappe.db.set_value("PDC Cheque", doc.name, "journal_entry", None)

    return je_name
