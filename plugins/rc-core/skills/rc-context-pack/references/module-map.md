# Module map

How the developer guide's modules map onto objects, and what each module decides in an
implementation. The object lists live in `sweep_org.py`; this file explains the shape.

## What belongs in the seed list

A module's parent objects are the obvious half. The half that gets forgotten, and did get
forgotten until 2026-11-25, is the other two kinds:

- **Configuration children.** The rule, condition, qualification or exclusion records that
  hang off a seeded parent and decide what it does. `AttributeBasedAdjRule` and
  `AttributeAdjustmentCondition` are the shape: without them, `AttributeBasedAdjustment`
  describes cleanly and tells you nothing about which attribute values select a price.
- **Transactional landing objects.** Where a computed result is written. An adjustment
  lands on `QuoteLinePriceAdjustment`, `OrderItemAdjustmentLineItem` and
  `AssetActionSrcPriceAdjustment`; an attribute value lands on `QuoteLineItemAttribute`,
  `OrderItemAttribute`, `AssetAttribute` and `AssetStatePeriodAttribute`.

A seed list with only parents fingerprints an org as provisioned while leaving every
question about *why a number came out that way* unanswerable from the pack.

## Product Catalog Management

`ProductCatalog` contains `ProductCategory`, which holds `Product2`. Classification and
attributes sit on `ProductClassification`, `AttributeDefinition` and
`ProductAttributeDefinition`.

The object that has no CPQ equivalent is `ProductSellingModel`. It carries
`SellingModelType` (OneTime, TermDefined, Evergreen), `PricingTerm`, `PricingTermUnit`
and `DoesAutoRenewAssetByDefault`. Pricing, bundle components, ramp segments and rate
cards all key off the selling model, not off the product alone. A product sold both
monthly and annually is one product with two selling models, where CPQ would often have
used two products or a term dimension. Get this wrong and every downstream artifact is wrong.

## Salesforce Pricing

`PricebookEntry` still carries list price. Everything above list price is a
`PriceAdjustmentSchedule`, whose `ScheduleType` is Volume, Term, Attribute, Bundle or
Custom, and whose `AdjustmentMethod` is Range or Slab. Tiers live on
`PriceAdjustmentTier`. `AttributeBasedAdjustment` and `BundleBasedAdjustment` bind a
schedule to the attribute or bundle context that selects it.

Map CPQ discount schedules, block prices and price rules here. A CPQ price rule that
computes rather than selects may have no declarative equivalent, and that is a finding
for the migration, not something to paper over.

## Bundles (Product Configurator)

Two objects, and both are needed. `ProductComponentGroup` is the group: it holds
`MinBundleComponents`, `MaxBundleComponents`, `Sequence`, and nests through
`ParentGroupId`. `ProductRelatedComponent` is the membership: `ParentProductRole`
(Bundle, Set, AddOn), `ChildProductRole`, `IsComponentRequired`, `IsDefaultComponent`,
`IsQuantityEditable`, `MinQuantity`, `MaxQuantity`, `QuantityScaleMethod` (Constant or
Proportional) and `DoesBundlePriceIncludeChild`.

CPQ's Product Feature maps to `ProductComponentGroup`; CPQ's Product Option maps to
`ProductRelatedComponent`. The mapping is close enough to be dangerous: option
constraints and configuration attributes do not map one-to-one, so verify rather than assume.

Those two objects describe what a bundle *contains*. What it is *allowed* to contain is the
`product_configurator` module, which the guide gives a section of its own:
`ProductConfigurationRule` holds the validation, inclusion and exclusion rules, scoped by
`ProcessScope` (Product, Bundle, Transaction) and `RuleSubType` (Product,
ProductClassification, BundleProduct, BundleProductClassification, Transaction).
`ProductConfigurationFlow` and `ProductConfigFlowAssignment` bind a configurator flow to a
product or classification. CPQ's Product Rules land here, not on the component objects.

`ExpressionSetConstraintObj` belongs to this module per the guide but is absent in
arm-picone, which the guide itself flags as documented in the Salesforce Object Reference
rather than here.

## Transaction Management

`Quote` with `QuoteLineItem`, `QuoteLineDetail`, `QuoteLineGroup` and
`QuoteLineRelationship`; `Order` with `OrderItem` and `OrderItemDetail`; then `Asset`,
`AssetStatePeriod` and `ContractItemPrice`. `SalesTransactionType` governs the
transaction. The Place Sales Transaction API is the entry point for creating and
amending quotes and orders headlessly.

The `*Detail` objects are where amendment and repricing history lives. Any migration
that reconstructs subscription history has to land it here.

## Billing

`BillingSchedule` is the spine and the busiest object in the model. It records
`BillingType` (Advance, Arrears), `BillingMethod` (OrderAmount, Evergreen, Usage),
`BillingTermUnit`, `Status`, and invoice grouping through `InvoiceGroupType` (Default,
BillingSchedule, Custom) plus `CustomInvoiceGroupKey`.

Its `Category` and `SubCategory` record why the schedule exists: Original, Renewal,
Cancellation, Amendment, with subcategories including SwapIn, SwapOut, UpgradeTo,
DowngradeFrom, DeltaPriceAmend, PriceAmend, ChangeEndDate, QuantityAmendment,
SimplifiedRenewal, AsIsRenewal, SimplifiedCancel and BillingFrequencyChange. That list
is effectively the catalogue of lifecycle changes the platform models natively. Check a
customer's required change types against it before designing anything custom.

`BillingPeriodItem` holds the periods, `InvoiceLine` links back to the schedule, and
`RevenueTransactionErrorLog` is where failures land. Check the error log before
concluding a transaction succeeded.

## Rate Management and Usage Management

`RateCard` and `RateCardEntry` with `RateAdjustmentByTier` and
`RateAdjustmentByAttribute` for usage rating; `UsageResource`, `ProductUsageGrant` and
`ProductUsageResourcePolicy` for entitlement and consumption. Only relevant if the
customer sells usage or credits. Check the fingerprint before designing around them.

## Dynamic Revenue Orchestrator and Advanced Approvals

Fulfilment orchestration and approvals. Frequently not provisioned. Treat as absent
until the fingerprint says otherwise.
