# suppliers_statements.py
# Copyright (c) 2025, xcode and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()

    invoices = get_invoices(filters)
    payments = get_payment_entries(filters)

    data = []

    # If nothing found at all, just return empty
    if not invoices and not payments:
        return columns, data

    # Combine data per supplier
    by_supplier = {}

    # --- Invoices as DEBIT entries ---
    for inv in invoices:
        supplier = inv["supplier"]
        by_supplier.setdefault(supplier, [])
        by_supplier[supplier].append({
            "entry_type": "Invoice",
            "posting_date": inv["posting_date"],
            "name": inv["name"],
            "bill_no": inv.get("bill_no"),
            "debit": flt(inv.get("grand_total")),
            "credit": 0.0,
            "supplier": supplier,
            "supplier_name": inv.get("supplier_name"),
        })

    # --- PDC Payment Entries as CREDIT entries ---
    for pe in payments:
        supplier = pe["supplier"]
        by_supplier.setdefault(supplier, [])
        by_supplier[supplier].append({
            "entry_type": "Payment",
            "posting_date": pe["posting_date"],
            "name": pe["name"],
            "bill_no": pe.get("reference_no") or pe.get("reference_date"),
            "debit": 0.0,
            "credit": flt(pe.get("paid_amount")),
            "supplier": supplier,
            "supplier_name": pe.get("supplier_name"),
        })

    # --- Build statement per supplier ---
    for supplier, rows in by_supplier.items():
        # Sort by date, then type, then name
        rows.sort(key=lambda d: (d["posting_date"], d["entry_type"], d["name"]))

        supplier_name = rows[0].get("supplier_name") or supplier

        # Supplier header row
        data.append({
            "supplier": supplier,
            "ref_inv": supplier_name,
            "bold": 1,
        })

        running = 0.0
        sum_debit = 0.0
        sum_credit = 0.0
        sum_pdc_credit = 0.0
        pdc_running = 0.0

        for row in rows:
            debit = flt(row["debit"])
            credit = flt(row["credit"])


            if row["entry_type"] == "Invoice":
                running += debit - credit
                sum_debit += debit
                sum_credit += credit
                ref = f"INV: {row['name']}"
                data.append({
                    "supplier": supplier,
                    "date": row["posting_date"],
                    "ref_inv": ref,
                    "bill_no": row.get("bill_no"),
                    "debit": debit,
                    "credit": credit,
                    "balance": running,
                })
            else:
                # ref = f"PDC: {row['name']}"
                # date = row["posting_date"]
                sum_pdc_credit += credit
                pdc_running += running - credit



        # TOTAL row
        data.append({
            "ref_inv": "Total",
            "debit": sum_debit,
            "credit": sum_credit,
            "balance": running,
            "bold": 1,
        })

        # NEW: PDC subtotal row under Total
        # Here all credits in this report are PDC payments (mode_of_payment='PDC', custom_deposit='No')
        data.append({
            "ref_inv": "PDC",
            "credit": sum_pdc_credit,
            "balance": pdc_running,
            "bold": 1,
            "indent": 1,
        })

    return columns, data


def get_columns():
    return [
        {
            "label": "Supplier",
            "fieldname": "supplier",
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 150,
        },
        {
            "label": "Date",
            "fieldname": "date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": "Reference",
            "fieldname": "ref_inv",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": "Bill No / Ref",
            "fieldname": "bill_no",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": "Debit",
            "fieldname": "debit",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "label": "Credit",
            "fieldname": "credit",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "label": "Balance",
            "fieldname": "balance",
            "fieldtype": "Currency",
            "width": 130,
        },
    ]


def get_invoices(filters):
    """Get Purchase Invoices (debit side)."""
    conditions = ["pi.docstatus = 1"]
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
            pi.posting_date,
            pi.name,
            pi.bill_no,
            pi.grand_total,
            pi.outstanding_amount,
            pi.supplier,
            s.supplier_name
        from `tabPurchase Invoice` pi
        left join `tabSupplier` s on s.name = pi.supplier
        where {' and '.join(conditions)}
        order by pi.supplier, pi.posting_date, pi.name
    """

    return frappe.db.sql(query, values, as_dict=True)


def get_payment_entries(filters):
    """
    Get PDC Payment Entries (credit side):
    - party_type = Supplier
    - mode_of_payment = 'PDC'
    - custom_deposit = 'No'
    """
    values = {}
    conditions = [
        "pe.docstatus = 1",
        "pe.payment_type = 'Pay'",
        "pe.party_type = 'Supplier'",
        "pe.mode_of_payment = 'PDC'",
        "pe.custom_deposit = 'No'",
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

    if filters.get("supplier"):
        conditions.append("pe.party = %(supplier)s")
        values["supplier"] = filters.supplier
    elif filters.get("supplier_group"):
        conditions.append("s.supplier_group = %(supplier_group)s")
        values["supplier_group"] = filters.supplier_group

    query = f"""
        select
            pe.posting_date,
            pe.name,
            pe.paid_amount,
            pe.party as supplier,
            s.supplier_name,
            pe.reference_no,
            pe.reference_date
        from `tabPayment Entry` pe
        left join `tabSupplier` s on s.name = pe.party
        where {' and '.join(conditions)}
        order by pe.party, pe.posting_date, pe.name
    """

    return frappe.db.sql(query, values, as_dict=True)
