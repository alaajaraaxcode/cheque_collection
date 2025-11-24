# Copyright (c) 2025, xcode and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()

	invoices = get_invoices(filters)

	data = []

	if not invoices:
		return columns, data

	# group by supplier
	by_supplier = {}
	for inv in invoices:
		by_supplier.setdefault(inv["supplier"], []).append(inv)

	for supplier, rows in by_supplier.items():
		supplier_name = rows[0].get("supplier_name") or supplier

		# Supplier header row
		data.append({
			"supplier": supplier,
			"ref_inv": f"{supplier_name}",
			"bold": 1,
		})

		running = 0.0
		sum_amount = 0.0
		sum_outstanding = 0.0

		for inv in rows:
			amount = flt(inv.get("grand_total"))
			outstanding = flt(inv.get("outstanding_amount"))
			running += outstanding
			sum_amount += amount
			sum_outstanding += outstanding

			data.append({
				"date": inv.get("posting_date"),
				"ref_inv": f"INV:{inv.get('name')}",
				"bill_no": inv.get("bill_no"),
				"amount": amount,
				"balance": outstanding,
				"cum_balance": running,
			})

		# Subtotal row for this supplier
		data.append({
			"ref_inv": "Total",
			"amount": sum_amount,
			"balance": sum_outstanding,
			"cum_balance": running,
			"bold": 1,
		})

		# PDC Amounts row
		pdc_amt = get_pdc_amount(supplier, filters)
		if pdc_amt:
			data.append({
				"ref_inv": "PDC Amounts",
				"balance": pdc_amt,
				"cum_balance": sum_outstanding + pdc_amt,
				"indent": 1,
				"bold": 1,
			})

	return columns, data


def get_columns():
	return [
		{"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 110},
		{"label": "Ref.No. INV #", "fieldname": "ref_inv", "fieldtype": "Data", "width": 220},
		{"label": "Bill No", "fieldname": "bill_no", "fieldtype": "Data", "width": 150},
		{"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": "Balance", "fieldname": "balance", "fieldtype": "Currency", "width": 120},
		{"label": "Cum.Balance", "fieldname": "cum_balance", "fieldtype": "Currency", "width": 130},
	]


def get_invoices(filters):
	conditions = ["pi.docstatus = 1", "pi.outstanding_amount > 0"]
	values = {}

	if filters.get("company"):
		conditions.append("pi.company = %(company)s")
		values["company"] = filters.company
	if filters.get("from_date"):
		conditions.append("pi.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("pi.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	if filters.get("supplier"):
		conditions.append("pi.supplier = %(supplier)s")
		values["supplier"] = filters.supplier
	elif filters.get("supplier_group"):
		conditions.append("s.supplier_group = %(supplier_group)s")
		values["supplier_group"] = filters.supplier_group

	query = f"""
		select
			pi.posting_date, pi.name, pi.bill_no, pi.grand_total, pi.outstanding_amount,
			pi.supplier, s.supplier_name
		from `tabPurchase Invoice` pi
		left join `tabSupplier` s on s.name = pi.supplier
		where {' and '.join(conditions)}
		order by pi.supplier, pi.posting_date, pi.name
	"""

	res = frappe.db.sql(query, values, as_dict=True)
	return res


def get_pdc_amount(supplier: str, filters):
	values = {"supplier": supplier}
	conditions = [
		"pe.docstatus = 1",
		"pe.payment_type = 'Pay'",
		"pe.party_type = 'Supplier'",
		"pe.party = %(supplier)s",
		"pe.mode_of_payment = 'PDC'",
		"(pe.custom_deposit = 'No' or pe.custom_deposit is null or pe.custom_deposit = '')",
	]

	if filters.get("company"):
		conditions.append("pe.company = %(company)s")
		values["company"] = filters.company
	if filters.get("from_date"):
		conditions.append("pe.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("pe.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	amt = frappe.db.sql(
		f"""
		select coalesce(sum(ifnull(pe.paid_amount, 0)), 0)
		from `tabPayment Entry` pe
		where {' and '.join(conditions)}
		""",
		values,
	)[0][0]

	return flt(amt)
