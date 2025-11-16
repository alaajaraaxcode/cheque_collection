// Copyright (c) 2025, xcode and contributors
// For license information, please see license.txt

frappe.ui.form.on("Payment Entry", {
    refresh: function(frm) {

        if (frm.doc.docstatus == 1 && frm.doc.payment_type === "Pay" && frm.doc.mode_of_payment === "PDC") {
            if (frm.doc.custom_journal_entry) {
                frm.add_custom_button(__('Return'), function() {
                    returnJournalEntry(frm);
                });
                // Optional: quick access to view
                frm.add_custom_button(__('View Journal Entry'), function() {
                    frappe.set_route('Form', 'Journal Entry', frm.doc.custom_journal_entry);
                }, __('Actions'));
            } else {
                frm.add_custom_button(__('PDC To Bank'), function() {
                    createJournalEntry(frm);
                }).addClass('btn-primary');
            }
        }
    },
    
    

});

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
                        default: frm.doc.paid_amount,
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
                        method: 'cheque_collection.api.create_journal_entry',
                        args: {
                            payment_entry_name: frm.doc.name,
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
    if (!frm.doc.custom_journal_entry) {
        frappe.msgprint(__('No Journal Entry linked.'));
        return;
    }

    frappe.confirm(
        __('Are you sure you want to return (cancel) the linked Journal Entry {0}?', [frm.doc.custom_journal_entry]),
        () => {
            frappe.call({
                method: 'cheque_collection.api.cancel_journal_entry',
                args: {
                    payment_entry_name: frm.doc.name
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
