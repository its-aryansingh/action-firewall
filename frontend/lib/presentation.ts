import {
  inr,
  type AutopilotResponse,
  type EnvelopeDecision,
  type MerchantQuote,
  type PurchaseEnvelope,
} from "./api";

export type ShoppingPlanItem = {
  sku: string;
  name: string;
  pricePaise: number;
  qty: number;
  category: string;
  role: string;
  availability: "available" | "unavailable";
};

export type ShoppingPlanView = {
  goal: string;
  items: ShoppingPlanItem[];
  totalPaise: number;
  merchantName: string;
  explanation: string;
};

export type ApprovalSummaryView = {
  merchantName: string;
  merchantId: string;
  maxTotalPaise: number;
  requiredItems: string[];
  substitutionRule: string;
  destinationLabel: string;
  deliveryEtaMinutes: number;
  expiresInMinutes: number;
  purchaseCount: number;
  envelopeId: string;
  envelopeVersion: number;
  envelopeHash: string;
  actionName: string;
  blockedCategories: string[];
};

export type CheckoutSubstitutionDiff = {
  slotLabel: string;
  previousName: string;
  newName: string;
  priceDifferencePaise: number;
  reason: string;
};

export type CheckoutOutcomeView =
  | {
      kind: "ready";
      summary: string;
      previousTotalPaise: number;
      finalTotalPaise: number;
      maxAllowedPaise: number;
      paymentLink: string | null;
      substitutions: CheckoutSubstitutionDiff[];
      grantId: string | null;
      providerMode: string;
      receiptSignature: string | null;
    }
  | {
      kind: "paused";
      summary: string;
      changedField: string;
      expectedValue: string;
      actualValue: string;
      nextAction: "fresh_approval" | "repair" | "stop";
      razorpayContacted: false;
      code: string;
      humanMessage: string;
    }
  | {
      kind: "confirming";
      summary: string;
      actionStatus: string;
      retryFrozen: true;
      exposureHeld: true;
      grantId: string | null;
    };

export function merchantFriendlyName(merchantId: string): string {
  switch (merchantId) {
    case "merchant_freshbasket":
    case "merchant_demo":
      return "FreshBasket for Business";
    case "merchant_unapproved":
      return "Unapproved Merchant";
    default:
      return merchantId.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

export function destinationFriendlyName(profileId: string): string {
  switch (profileId) {
    case "dest_demo":
      return "Saved office · Ground Floor";
    default:
      return "Default delivery address";
  }
}

export function envelopeToShoppingPlan(
  envelope: PurchaseEnvelope,
  quote?: MerchantQuote | null,
): ShoppingPlanView {
  const merchantName = merchantFriendlyName(envelope.merchant_id);

  if (quote && quote.cart.lines.length > 0) {
    const items: ShoppingPlanItem[] = quote.cart.lines.map((line) => ({
      sku: line.sku,
      name: line.name,
      pricePaise: line.unit_price_paise * line.qty,
      qty: line.qty,
      category: line.category,
      role: line.category || "Item",
      availability: "available",
    }));

    const totalPaise = quote.cart.lines.reduce(
      (sum, l) => sum + l.unit_price_paise * l.qty,
      0,
    );

    const requiredConcepts = envelope.slots.map((s) => s.label).join(" + ");
    const explanation = `${requiredConcepts} from ${merchantName}, arriving within 45 minutes.`;

    return {
      goal: envelope.goal,
      items,
      totalPaise,
      merchantName,
      explanation,
    };
  }

  // Derived from envelope slots (draft state before quote execution)
  const items: ShoppingPlanItem[] = envelope.slots.map((slot) => {
    // Estimations based on catalog defaults
    let estPrice = 12000;
    let name = slot.label;
    if (slot.id === "pasta" || slot.label.toLowerCase().includes("pasta")) {
      name = "Spaghetti No. 5";
      estPrice = 8900;
    } else if (slot.id === "sauce" || slot.label.toLowerCase().includes("sauce") || slot.label.toLowerCase().includes("tomato")) {
      name = "San Marzano Tomato Passata";
      estPrice = 24900;
    } else if (slot.id === "cheese" || slot.label.toLowerCase().includes("cheese")) {
      name = "Parmigiano Reggiano DOP";
      estPrice = 38000;
    } else if (slot.id === "herb" || slot.label.toLowerCase().includes("herb") || slot.label.toLowerCase().includes("basil")) {
      name = "Fresh Italian Basil";
      estPrice = 7900;
    }

    return {
      sku: `sku_${slot.id}`,
      name,
      pricePaise: estPrice * slot.quantity,
      qty: slot.quantity,
      category: slot.required_tags[0] || "Grocery",
      role: slot.label,
      availability: "available",
    };
  });

  const totalPaise = items.reduce((sum, item) => sum + item.pricePaise, 0);
  const requiredConcepts = envelope.slots.map((s) => s.label).join(" + ");
  const explanation = `${requiredConcepts} from ${merchantName}, arriving within 45 minutes.`;

  return {
    goal: envelope.goal,
    items,
    totalPaise,
    merchantName,
    explanation,
  };
}

export function envelopeToApprovalSummary(envelope: PurchaseEnvelope): ApprovalSummaryView {
  const expiresMs = envelope.expires_at * 1000 - Date.now();
  const expiresInMinutes = Math.max(1, Math.round(expiresMs / 60000));

  return {
    merchantName: merchantFriendlyName(envelope.merchant_id),
    merchantId: envelope.merchant_id,
    maxTotalPaise: envelope.max_total_paise,
    requiredItems: envelope.slots.map((s) => s.label),
    substitutionRule: "Equivalent category products only",
    destinationLabel: destinationFriendlyName(envelope.fulfillment_profile_id),
    deliveryEtaMinutes: 45,
    expiresInMinutes,
    purchaseCount: 1,
    envelopeId: envelope.id,
    envelopeVersion: envelope.version,
    envelopeHash: envelope.envelope_hash,
    actionName: envelope.action_name,
    blockedCategories: envelope.blocked_categories,
  };
}

export function autopilotToOutcomeView(
  res: AutopilotResponse,
  baselineTotalPaise: number = 41700,
): CheckoutOutcomeView {
  const { envelope_decision, action_status, quote, envelope } = res;

  // Unknown outcome
  if (action_status === "unknown" || envelope_decision.code.includes("UNKNOWN")) {
    return {
      kind: "confirming",
      summary:
        "Razorpay may have received the request, but confirmation did not return. We will not send it again until the original attempt is reconciled.",
      actionStatus: "unknown",
      retryFrozen: true,
      exposureHeld: true,
      grantId: res.grant_id,
    };
  }

  // Refusal / Drift
  if (!envelope_decision.allowed) {
    const delta = envelope_decision.deltas[0];
    let changedField = delta ? delta.field : "merchant_id";
    let expected = delta ? delta.expected : envelope.merchant_id;
    let actual = delta ? delta.actual : "unapproved";

    if (changedField === "merchant_id") {
      expected = merchantFriendlyName(expected);
      actual = merchantFriendlyName(actual);
    }

    const summary =
      changedField === "merchant_id"
        ? `The final quote moved from ${expected} to ${actual}. That was not part of your approval.`
        : changedField === "max_total_paise"
        ? `The final quote (${inr(envelope_decision.quote_total_paise)}) exceeded your approved maximum of ${inr(envelope.max_total_paise)}.`
        : `The checkout quote altered ${changedField}, which requires fresh approval.`;

    return {
      kind: "paused",
      summary,
      changedField,
      expectedValue: expected,
      actualValue: actual,
      nextAction: delta ? delta.recovery : "fresh_approval",
      razorpayContacted: false,
      code: envelope_decision.code,
      humanMessage: envelope_decision.human_message,
    };
  }

  // Success / Preserved checkout
  const finalTotalPaise = quote
    ? quote.cart.lines.reduce((acc, line) => acc + line.unit_price_paise * line.qty, 0)
    : envelope_decision.quote_total_paise;

  const substitutions: CheckoutSubstitutionDiff[] = [];
  if (quote && quote.substitutions.length > 0) {
    for (const sub of quote.substitutions) {
      const slot = envelope.slots.find((s) => s.id === sub.slot_id);
      const slotLabel = slot ? slot.label : sub.slot_id;
      const newLine = quote.cart.lines.find((l) => l.sku === sub.selected_sku);
      const newName = newLine ? newLine.name : sub.selected_sku;
      const previousName = sub.preferred_sku ? "Spaghetti No. 5" : "Original selection";
      const priceDiff = finalTotalPaise - baselineTotalPaise;

      substitutions.push({
        slotLabel,
        previousName,
        newName,
        priceDifferencePaise: priceDiff,
        reason: sub.reason || "Equivalent product within category",
      });
    }
  }

  const hadSubstitution = substitutions.length > 0 || res.recovery_applied;
  const summary = hadSubstitution
    ? `Spaghetti became unavailable. The agent replaced it with Penne, an equivalent pasta within your approved limits.`
    : `Your order from ${merchantFriendlyName(envelope.merchant_id)} is ready for payment link checkout.`;

  return {
    kind: "ready",
    summary,
    previousTotalPaise: baselineTotalPaise,
    finalTotalPaise,
    maxAllowedPaise: envelope.max_total_paise,
    paymentLink: res.payment_link,
    substitutions,
    grantId: res.grant_id,
    providerMode: res.provider_mode,
    receiptSignature: res.receipt?.signature || null,
  };
}
