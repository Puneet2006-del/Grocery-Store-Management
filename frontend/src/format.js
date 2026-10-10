export const inr = (n) => `₹${Number(n ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

export const describeAction = (r) =>
  r.actionType === 'MARKDOWN'
    ? `Markdown ${Number(r.markdownPct)}%`
    : r.actionType === 'TRANSFER'
      ? `Transfer ${r.quantity} units to ${r.counterpartStoreName ?? r.counterpartStoreId}`
      : `Urgent order of ${r.quantity} units`
