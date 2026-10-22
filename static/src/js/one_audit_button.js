/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class OneAuditButton extends Component {
  static template = "zofirm_contract.OneAuditButton";

  setup() {
    this.orm = useService("orm");
    this.action = useService("action");
    this.state = useState({
      oneAuditCount: 0,
      visible: false,
    });

    onWillStart(async () => {
      const result = await this.orm.call(
        "zofirm.one.audit",
        "get_one_audit_ui_info",
        []
      );

      this.state.visible = !!result?.visible;

      if (this.state.visible) {
        this.state.oneAuditCount = result?.count || 0;
      }
    });
  }

  async openOneAudit() {
    if (!this.state.visible) {
      return;
    }
    await this.action.doAction("zofirm_contract.action_one_audit");
  }
}