# Copyright (c) 2025, xcode and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()

	conditions = [
		"pe.docstatus = 1",
		"pe.payment_type = 'Pay'",
		"pe.mode_of_payment = 'PDC'",
		"(pe.custom_journal_entry is null or pe.custom_journal_entry = '')"
	]
	values = {}

	if filters.get("reference_no"):
		conditions.append("pe.reference_no like %(reference_no)s")
		values["reference_no"] = f"%{filters.reference_no}%"

	payment_query = f"""
		select
			pe.name as payment_entry_name,
			pe.reference_no,
			pe.reference_date,
			pe.posting_date,
			pe.paid_amount,
			pe.party as supplier,
			s.supplier_name
		from `tabPayment Entry` pe
		left join `tabSupplier` s on s.name = pe.party
		where {' and '.join(conditions)}
		order by pe.reference_date, pe.name
	"""

	payments = frappe.db.sql(payment_query, values, as_dict=True)

	if not payments:
		return columns, []

	data = []
	for payment in payments:
		data.append(
			{
				"payment_entry_name": payment.get("payment_entry_name"),
				"reference_no": payment.get("reference_no"),
				"reference_date": payment.get("reference_date"),
				"posting_date": payment.get("posting_date"),
				"supplier": payment.get("supplier"),
				"supplier_name": payment.get("supplier_name"),
				"paid_amount": payment.get("paid_amount"),
			}
		)

	return columns, data


def get_columns():
	return [
		{"label": "Payment Entry", "fieldname": "payment_entry_name", "fieldtype": "Link", "options": "Payment Entry", "width": 160},
		{"label": "Cheque No", "fieldname": "reference_no", "fieldtype": "Data", "width": 140},
		{"label": "Cheque Date", "fieldname": "reference_date", "fieldtype": "Date", "width": 120},
		{"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 120},
		{"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": "Supplier Name", "fieldname": "supplier_name", "fieldtype": "Data", "width": 220},
		{"label": "Paid Amount", "fieldname": "paid_amount", "fieldtype": "Currency", "width": 120},
	]
