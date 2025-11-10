// Copyright (c) 2025, xcode and contributors
// For license information, please see license.txt

frappe.ui.form.on("PDC Cheque", {
    validate: function(frm) {
        let partySet = new Set();
        frm.doc.references.forEach(row => {
            if (partySet.has(row.party)) {
                frappe.throw(__('Party {0} is already added. Please avoid duplicates.', [row.party]));
            }
            partySet.add(row.party);
        });
    },

    refresh: function(frm) {
        if (frm.doc.docstatus != 1) {
            frm.add_custom_button(__('Edit Invoices'), function() {
                showCustomerSelectionPrompt(frm, editCustomerInvoicesPrompt);
            });
            frm.doc.references.forEach(reference_row => {
                updateTotalPaidInReference(frm, reference_row.party);
            });
        }
        if (frm.doc.docstatus == 1) {
            if (frm.doc.journal_entry) {
                frm.add_custom_button(__('Return'), function() {
                    returnJournalEntry(frm);
                });
                // Optional: quick access to view
                frm.add_custom_button(__('View Journal Entry'), function() {
                    frappe.set_route('Form', 'Journal Entry', frm.doc.journal_entry);
                }, __('Actions'));
            } else {
                frm.add_custom_button(__('PDC To Bank'), function() {
                    createJournalEntry(frm);
                }).addClass('btn-primary');
            }
        }
        // frm.set_query("mode_of_payment", function () {
			
		// 	return {
		// 		filters: {
		// 			name: ["in",["Cash","PDC","CASH AL AIN","CASH FUJ"] ],
		// 		},
		// 	};
		// });
        // frm.set_value("mode_of_payment", "PDC");
        // frm.refresh_field("mode_of_payment");

        frm.set_query("employee", function () {
			
			return {
				filters: {
					designation: ["in",["Cheque Collection"] ],
				},
			};
		});
    },
    
    

});


frappe.ui.form.on('PDC Cheque Entry Reference', {
    party: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        frm.fields_dict['references'].grid.get_field('party').get_query = function() {
            let added_parties = frm.doc.references.map(reference_row => reference_row.party);

            return {
                filters: [
                    ['name', 'not in', added_parties]
                ]
            };
        };

        if (row.party) {
            fetchCustomerInvoices(frm, row);
            frm.fields_dict['references'].grid.grid_rows_by_docname[cdn].toggle_editable('party', false);
            frm.refresh_field('references');
        }
    },
    
    refresh: function(frm) {
        frm.doc.references.forEach(function(row) {
            frm.fields_dict['references'].grid.grid_rows_by_docname[row.name].toggle_editable('party', false);
        });
        frm.refresh_field('references');
    }
});

function getSelectedReferenceRow(frm) {
    let selected_row = null;
    frm.doc.references.forEach(row => {
        if (row.__checked) {
            selected_row = row;
        }
    });
    return selected_row;
}

function fetchCustomerInvoices(frm, row) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Sales Invoice',
            filters: {
                customer: row.party,
                docstatus: 1,
                outstanding_amount: ['>', 0]
            },
            fields: ['name', 'outstanding_amount', 'grand_total'],
            limit_page_length: null
        },
        callback: function(response) {
            if (response.message && response.message.length > 0) {
                openInvoiceSelectionDialog(frm, row, response.message);
            } else {
                frappe.msgprint(__('No outstanding invoices found for the selected customer.'));
            }
        }
    });
}

function openInvoiceSelectionDialog(frm, row, invoices) {
    const dialogFields = buildInvoiceDialogFields(frm, invoices);

    const dialog = new frappe.ui.Dialog({
        title: __('Outstanding Invoices for ') + row.party,
        fields: dialogFields,
        size: "extra-large",
        primary_action_label: __('Update Invoices'),
        primary_action(values) {
            processInvoices(frm, values.invoices, row, dialog);
        }
    });

    frappe.dom.unfreeze();
    dialog.show();
}

function buildInvoiceDialogFields(frm, invoices) {
    return [{
        fieldname: 'invoices',
        fieldtype: 'Table',
        label: 'Outstanding Invoices',
        cannot_add_rows: true,
        cannot_delete_rows: true,
        fields: getInvoiceFields(frm),
        data: invoices.map(invoice => ({
            reference_name: invoice.name,
            grand_total: invoice.grand_total,
            outstanding_amount: invoice.outstanding_amount,
            paid_amount: 0
        })),
        get_data: () => invoices.map(invoice => invoice)
    }];
}

function getInvoiceFields(frm) {
    return [
        {
            fieldname: 'reference_name',
            fieldtype: 'Link',
            label: 'Invoice Number',
            options: 'Sales Invoice',
            in_list_view: 1,
            read_only: 1
        },
        {
            fieldname: 'grand_total',
            fieldtype: 'Currency',
            label: 'Grand Total',
            in_list_view: 1,
            read_only: 1
        },
        {
            fieldname: 'outstanding_amount',
            fieldtype: 'Currency',
            label: 'Outstanding Amount',
            in_list_view: 1,
            read_only: 1
        },
        {
            fieldname: 'paid_amount',
            fieldtype: 'Currency',
            label: 'Paid Amount',
            in_list_view: 1
        }
    ];
}

function processInvoices(frm, invoices, row, dialog) {
    invoices.forEach(invoice => {
        if (invoice.paid_amount > 0) {
            addInvoiceToTable(frm, row.party, invoice);
        }
    });

    dialog.hide();
    frm.refresh_field('invoices');
    updateTotalPaidInReference(frm, row.party);
}

function addInvoiceToTable(frm, party, invoice) {
    var invoice_row = frm.add_child('invoices');
    frappe.model.set_value(invoice_row.doctype, invoice_row.name, 'customer', party);
    frappe.model.set_value(invoice_row.doctype, invoice_row.name, 'reference_type', 'Sales Invoice');
    frappe.model.set_value(invoice_row.doctype, invoice_row.name, 'reference_name', invoice.reference_name);
    frappe.model.set_value(invoice_row.doctype, invoice_row.name, 'outstanding_amount', invoice.outstanding_amount);
    frappe.model.set_value(invoice_row.doctype, invoice_row.name, 'grand_total', invoice.grand_total);
    frappe.model.set_value(invoice_row.doctype, invoice_row.name, 'paid_amount', invoice.paid_amount);
}

function removeCustomerInvoices(frm, party) {
    let to_remove = frm.doc.invoices.filter(invoice => invoice.customer === party);
    to_remove.forEach(invoice => {
        let idx = frm.doc.invoices.findIndex(i => i.reference_name === invoice.reference_name);
        if (idx !== -1) {
            frm.get_field('invoices').grid.grid_rows[idx].remove();
        }
    });
    frm.refresh_field('invoices');
}

function cleanCustomerInvoices(frm, party) {
    removeCustomerInvoices(frm, party);
    frappe.msgprint(__('All invoices for {0} have been cleaned.', [party]));
}
function createJournalEntry(frm) {
    // Fetch Bank accounts for the company
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Account',
            filters: {
                account_type: 'Bank',
                is_group: 0,
                company: frm.doc.company,
                disabled: 0
            },
            fields: ['name', 'account_name'],
            limit_page_length: 500
        },
        callback: function(r) {
            const accounts = (r.message || []).map(acc => ({
                label: `${acc.account_name || acc.name} (${acc.name})`,
                value: acc.name
            }));

            if (accounts.length === 0) {
                frappe.msgprint(__('No bank accounts found for the company.'));
                return;
            }

            const d = new frappe.ui.Dialog({
                title: __('PDC To Bank'),
                fields: [
                    {
                        fieldname: 'bank_account',
                        fieldtype: 'Select',
                        label: __('Select Bank Account'),
                        options: accounts,
                        reqd: 1
                    },
                    {
                        fieldname: 'amount',
                        fieldtype: 'Currency',
                        label: __('Amount'),
                        default: frm.doc.amount,
                        read_only: 1
                    }
                ],
                primary_action_label: __('Create Journal Entry'),
                primary_action(values) {
                    if (!values.bank_account) {
                        frappe.msgprint(__('Please select a bank account.'));
                        return;
                    }

                    d.hide();
                    frappe.call({
                        method: 'cheque_collection.cheque_collection.doctype.pdc_cheque.pdc_cheque.create_journal_entry',
                        args: {
                            pdc_cheque_name: frm.doc.name,
                            bank_account: values.bank_account
                        },
                        freeze: true,
                        freeze_message: __('Creating Journal Entry...'),
                        callback: function(res) {
                            if (res.message) {
                                const je_name = res.message;
                                frappe.msgprint(__('Journal Entry {0} created successfully.', [je_name]));
                                // Reload to fetch updated journal_entry link and toggle buttons
                                frm.reload_doc();
                                frappe.set_route('Form', 'Journal Entry', je_name);
                            }
                        }
                    });
                }
            });

            d.show();
        }
    });
}

function returnJournalEntry(frm) {
    if (!frm.doc.journal_entry) {
        frappe.msgprint(__('No Journal Entry linked.'));
        return;
    }

    frappe.confirm(
        __('Are you sure you want to return (cancel) the linked Journal Entry {0}?', [frm.doc.journal_entry]),
        () => {
            frappe.call({
                method: 'cheque_collection.cheque_collection.doctype.pdc_cheque.pdc_cheque.cancel_journal_entry',
                args: {
                    pdc_cheque_name: frm.doc.name
                },
                freeze: true,
                freeze_message: __('Cancelling Journal Entry...'),
                callback: function(res) {
                    if (!res.exc) {
                        frappe.msgprint(__('Journal Entry cancelled successfully.'));
                        frm.reload_doc();
                    }
                }
            });
        }
    );
}

function showCustomerSelectionPrompt(frm, actionCallback) {
    let customerOptions = frm.doc.references.map(row => ({
        label: row.party_name || row.party,
        value: row.party
    }));

    if (customerOptions.length === 0) {
        frappe.msgprint(__('No parties available for selection.'));
        return;
    }

    let dialog = new frappe.ui.Dialog({
        title: __('Select Customer'),
        fields: [
            {
                fieldname: 'customer',
                label: __('Customer'),
                fieldtype: 'Select',
                options: customerOptions
            }
        ],
        primary_action_label: __('Select'),
        primary_action: function(values) {
            let selectedCustomer = values.customer;
            if (selectedCustomer) {
                actionCallback(frm, selectedCustomer);
                dialog.hide();
            } else {
                frappe.msgprint(__('Please select a customer.'));
            }
        }
    });

    dialog.show();
}

function editCustomerInvoicesPrompt(frm, customer) {
    let invoices = frm.doc.invoices.filter(invoice => invoice.customer === customer);

    if (invoices.length === 0) {
        frappe.msgprint(__('No invoices found for the selected customer.'));
        return;
    }

    const dialogFields = [{
        fieldname: 'invoices',
        fieldtype: 'Table',
        label: 'Edit Invoices',
        cannot_add_rows: true,
        cannot_delete_rows: true,
        fields: getEditInvoiceFields(frm),
        data: invoices.map(invoice => ({
            reference_name: invoice.reference_name,
            grand_total: invoice.grand_total,
            outstanding_amount: invoice.outstanding_amount,
            paid_amount: invoice.paid_amount,
            remove: 0 
        })),
        get_data: () => invoices.map(invoice => invoice)
    }];

    let dialog = new frappe.ui.Dialog({
        title: __('Edit Or Remove Invoices for ') + customer,
        size: "extra-large",
        fields: dialogFields,
        primary_action_label: __('Update Invoices'),
        primary_action(values) {
            values.invoices.forEach(invoice => {
                if (invoice.remove) {
                    removeInvoiceFromTable(frm, invoice.reference_name, customer);
                } else {
                    updateInvoiceInTable(frm, customer, invoice);
                }
            });
            frm.refresh_field('invoices');
            dialog.hide();
        }
    });

    dialog.show();
}

function removeInvoiceFromTable(frm, reference_name, customer) {
    let invoice_row = frm.doc.invoices.find(invoice => invoice.reference_name === reference_name);
    if (invoice_row) {
        frappe.model.clear_doc("Invoices", invoice_row.name);
        frm.refresh_field('invoices');
    }
    updateTotalPaidInReference(frm, customer)
}

function updateInvoiceInTable(frm, customer, invoice) {
    let invoice_row = frm.doc.invoices.find(row => row.reference_name === invoice.reference_name && row.customer === customer);
    if (invoice_row) {
        frappe.model.set_value(invoice_row.doctype, invoice_row.name, 'paid_amount', invoice.paid_amount);
        frappe.model.set_value(invoice_row.doctype, invoice_row.name, 'outstanding_amount', invoice.outstanding_amount);
        updateTotalPaidInReference(frm, customer)
    }
}

function getEditInvoiceFields(frm) {
    return [
        {
            fieldname: 'reference_name',
            fieldtype: 'Link',
            label: 'Invoice Number',
            options: 'Sales Invoice',
            in_list_view: 1,
            read_only: 1
        },
        {
            fieldname: 'grand_total',
            fieldtype: 'Currency',
            label: 'Grand Total',
            in_list_view: 1,
            read_only: 1
        },
        {
            fieldname: 'outstanding_amount',
            fieldtype: 'Currency',
            label: 'Outstanding Amount',
            in_list_view: 1,
            read_only: 1
        },
        {
            fieldname: 'paid_amount',
            fieldtype: 'Currency',
            label: 'Paid Amount',
            in_list_view: 1
        },
        {
            fieldname: 'remove',
            fieldtype: 'Check',
            label: 'Remove',
            in_list_view: 1,
        }
    ];
}
function updateTotalPaidInReference(frm, customer) {
    let total_paid = frm.doc.invoices
        .filter(invoice => invoice.customer === customer)
        .reduce((sum, invoice) => sum + (invoice.paid_amount || 0), 0);

    let reference_row = frm.doc.references.find(row => row.party === customer);
    if (reference_row) {
        frappe.model.set_value(reference_row.doctype, reference_row.name, 'total_paid', total_paid);
    }

    frm.refresh_field('references');
}