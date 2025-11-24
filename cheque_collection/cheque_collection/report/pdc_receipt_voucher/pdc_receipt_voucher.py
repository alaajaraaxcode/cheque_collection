# Copyright (c) 2025, xcode and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()

	conditions = ["pc.docstatus = 1", "(pc.journal_entry is null or pc.journal_entry = '')"]
	values = {}

	if filters.get("reference_no"):
		conditions.append("pc.reference_no like %(reference_no)s")
		values["reference_no"] = f"%{filters.reference_no}%"

	cheque_query = f"""
		select
			pc.name as pdc_name,
			pc.reference_no,
			pc.reference_date,
			pc.posting_date,
			pc.amount as cheque_amount
		from `tabPDC Cheque` pc
		where {' and '.join(conditions)}
		order by pc.reference_date, pc.name
	"""

	cheques = frappe.db.sql(cheque_query, values, as_dict=True)

	if not cheques:
		return columns, []

	# Fetch all invoice child rows for returned cheques
	cheque_names = [c["pdc_name"] for c in cheques]
	invoice_rows = frappe.db.sql(
		"""
		select
			inv.parent as pdc_name,
			inv.customer,
			inv.customer_name,
			inv.reference_name as invoice_no,
			inv.grand_total,
			inv.paid_amount,
			inv.outstanding_amount
		from `tabPDC Cheque Invoices` inv
		where inv.parent in (%s)
		order by inv.parent, inv.reference_name
		""" % ",".join(["%s"] * len(cheque_names)),
		cheque_names,
		as_dict=True,
	)

	by_cheque = {}
	for r in invoice_rows:
		by_cheque.setdefault(r["pdc_name"], []).append(r)

	data = []
	for cheque in cheques:
		cname = cheque["pdc_name"]
		data.append(
			{
				"pdc_name": cname,
				"reference_no": cheque.get("reference_no"),
				"reference_date": cheque.get("reference_date"),
				"posting_date": cheque.get("posting_date"),
				"cheque_amount": cheque.get("cheque_amount"),
				"bold": 1,
			}
		)

		rows = by_cheque.get(cname, [])
		total = 0.0
		for r in rows:
			amt = r.get("paid_amount") or 0.0
			total += amt
			data.append(
				{
					"customer": r.get("customer"),
					"customer_name": r.get("customer_name"),
					"invoice_no": r.get('invoice_no'),
					"amount": amt,
					"indent": 1,
				}
			)

		# Total row under invoices
		data.append(
			{
				"customer_name": "Total",
				"amount": total,
				"bold": 1,
				"indent": 1,
			}
		)

	return columns, data


def get_columns():
	return [
		{"label": "PDC Name", "fieldname": "pdc_name", "fieldtype": "Link", "options": "PDC Cheque", "width": 140},
		{"label": "Cheque No", "fieldname": "reference_no", "fieldtype": "Data", "width": 140},
		{"label": "Cheque Date", "fieldname": "reference_date", "fieldtype": "Datetime", "width": 150},
		{"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Datetime", "width": 150},
		{"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": "Customer Name", "fieldname": "customer_name", "fieldtype": "Data", "width": 220},
		{"label": "Invoice No.", "fieldname": "invoice_no", "fieldtype": "Data", "width": 140},
		{"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 120},
	]
