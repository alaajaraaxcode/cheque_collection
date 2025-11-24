// suppliers_statements.js
// Copyright (c) 2025, xcode and contributors
// For license information, please see license.txt

frappe.query_reports["Suppliers Statements"] = {
    filters: [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "company",
            label: "Company",
            fieldtype: "Link",
            options: "Company",
            reqd: 0,
        },
        {
            fieldname: "supplier",
            label: "Supplier",
            fieldtype: "Link",
            options: "Supplier",
            reqd: 0,
        },
        {
            fieldname: "supplier_group",
            label: "Supplier Group",
            fieldtype: "Link",
            options: "Supplier Group",
            reqd: 0,
            depends_on: "eval:!doc.supplier",
        },
    ],
};
