/** @odoo-module **/

import { SaleOrderLineProductField } from "@sale/js/sale_product_field";
import { patch } from "@web/core/utils/patch";


const ARABIC_RE = /[\u0600-\u06FF]/;


patch(SaleOrderLineProductField.prototype, {

    get productName() {
        const data = this.props.record.data;

        if (this.props.name === "product_template_id") {

            const currentTemplateId =
                data.product_template_id?.id;

            const savedTemplateId =
                data.zofirm_product_display_template_id?.id;

            if (
                data.zofirm_product_display_name &&
                currentTemplateId &&
                savedTemplateId &&
                currentTemplateId === savedTemplateId
            ) {
                return data.zofirm_product_display_name;
            }
        }

        return super.productName;
    },

    get m2oProps() {

        const props = super.m2oProps;

        if (this.props.name !== "product_template_id") {
            return props;
        }

        return {
            ...props,

            update: async (value) => {

                let selectedId = false;
                let selectedName = false;
                let selectedLang = false;

                if (value?.id) {

                    selectedId = value.id;

                    selectedName = (
                        value.display_name || ""
                    )
                        .split("\n")[0]
                        .trim();

                    selectedLang =
                        ARABIC_RE.test(selectedName)
                            ? "ar_001"
                            : "en_US";
                }

                const result =
                    await props.update(value);

                if (!value) {

                    await this.props.record.update({

                        zofirm_product_display_name:
                            false,

                        zofirm_product_display_lang:
                            false,

                        zofirm_product_display_template_id:
                            false,
                    });

                    return result;
                }

                if (!selectedId) {
                    return result;
                }

                await this.props.record.update({

                    zofirm_product_display_name:
                        selectedName || false,

                    zofirm_product_display_lang:
                        selectedLang,

                    zofirm_product_display_template_id: {
                        id: selectedId,
                        display_name:
                            value.display_name,
                    },
                });

                return result;
            },
        };
    },
});