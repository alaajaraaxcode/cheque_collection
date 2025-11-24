# Copyright (c) 2025, xcode and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


# ANSI = {
# 	"RED": "\033[31m",
# 	"GREEN": "\033[32m",
# 	"YELLOW": "\033[33m",
# 	"BLUE": "\033[34m",
# 	"MAGENTA": "\033[35m",
# 	"CYAN": "\033[36m",
# 	"RESET": "\033[0m",
# }


# def cprint(label, value=None, color="CYAN"):
# 	try:
# 		col = ANSI.get(color, "")
# 		end = ANSI["RESET"]
# 		if value is None:
# 			print(f"{col}[Customers Statements] {label}{end}")
# 		else:
# 			print(f"{col}[Customers Statements] {label}:{end} {value}")
# 	except Exception:
# 		# Never fail the report because of printing
# 		pass


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()

	# cprint("Incoming Filters", dict(filters), color="YELLOW")

	invoices = get_invoices(filters)

	data = []

	if not invoices:
		# cprint("No invoices matched primary query", color="RED")
		return columns, data

	# group by customer
	by_customer = {}
	for inv in invoices:
		by_customer.setdefault(inv["customer"], []).append(inv)

	# cprint("Customers Found", list(by_customer.keys()), color="GREEN")

	for customer, rows in by_customer.items():
		customer_name = rows[0].get("customer_name") or customer

		# Customer header row
		data.append({
			"customer": customer,
			"ref_inv": f"{customer_name}",
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

			# Log each invoice briefly
			# cprint(
			# 	"Row",
			# 	{
			# 		"date": str(inv.get("posting_date")),
			# 		"inv": inv.get("name"),
			# 		"amount": amount,
			# 		"outstanding": outstanding,
			# 		"running": running,
			# 	},
			# 	color="BLUE",
			# )

			data.append({
				"date": inv.get("posting_date"),
				"ref_inv": f"INV:{inv.get('name')}",
				"po_no": inv.get("po_no"),
				"amount": amount,
				"balance": outstanding,
				"cum_balance": running,
				"c_type": "CASH" if inv.get("is_pos") else "CREDIT",
			})

		# Subtotal row for this customer
		data.append({
			"ref_inv": "Total",
			"amount": sum_amount,
			"balance": sum_outstanding,
			"cum_balance": running,
			"bold": 1,
		})

		# PDC Amounts row
		pdc_amt = get_pdc_amount(customer, filters)
		# cprint("PDC Sum", {"customer": customer, "pdc": pdc_amt}, color="MAGENTA")
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
		{"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 110},
		{"label": "Ref.No. INV #", "fieldname": "ref_inv", "fieldtype": "Data", "width": 220},
		{"label": "PO", "fieldname": "po_no", "fieldtype": "Data", "width": 150},
		{"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": "Balance", "fieldname": "balance", "fieldtype": "Currency", "width": 120},
		{"label": "Cum.Balance", "fieldname": "cum_balance", "fieldtype": "Currency", "width": 130},
		{"label": "C_Type", "fieldname": "c_type", "fieldtype": "Data", "width": 90},
	]


def get_invoices(filters):
	conditions = ["si.docstatus = 1", "si.outstanding_amount > 0"]
	values = {}

	if filters.get("company"):
		conditions.append("si.company = %(company)s")
		values["company"] = filters.company
	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	if filters.get("customer"):
		conditions.append("si.customer = %(customer)s")
		values["customer"] = filters.customer
	elif filters.get("customer_group"):
		conditions.append("c.customer_group = %(customer_group)s")
		values["customer_group"] = filters.customer_group

	query = f"""
		select
			si.posting_date, si.name, si.po_no, si.grand_total, si.outstanding_amount,
			si.is_pos, si.customer, c.customer_name
		from `tabSales Invoice` si
		left join `tabCustomer` c on c.name = si.customer
		where {' and '.join(conditions)}
		order by si.customer, si.posting_date, si.name
	"""

	# cprint("SQL Conditions", " and ".join(conditions), color="YELLOW")
	# cprint("SQL Values", values, color="YELLOW")

	res = frappe.db.sql(query, values, as_dict=True)
	# cprint("Invoices Count", len(res), color="GREEN")

	# If nothing came back, try to probe without outstanding filter and print counts
	# if not res:
	# 	probe_conditions = [c for c in conditions if "outstanding_amount" not in c]
	# 	probe_query = query.replace(" where " + " and ".join(conditions), " where " + " and ".join(probe_conditions))
	# 	probe = frappe.db.sql(probe_query, values, as_dict=True)


	return res


def get_pdc_amount(customer: str, filters):
	values = {"customer": customer}
	conditions = [
		"pe.docstatus = 1",
		"pe.payment_type = 'Receive'",
		"pe.party_type = 'Customer'",
		"pe.party = %(customer)s",
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
		select coalesce(sum(ifnull(pe.received_amount, ifnull(pe.paid_amount, 0))), 0)
		from `tabPayment Entry` pe
		where {' and '.join(conditions)}
		""",
		values,
	)[0][0]

	return flt(amt)