/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { OneAuditButton } from "./one_audit_button";

patch(ListController.prototype, {
  setup() {
    super.setup(...arguments);

    this.showOneAuditBtn = this.props?.resModel === "zofirm.contract";

    if (this.showOneAuditBtn) {
      this.OneAuditButton = OneAuditButton;
    }
  },
});