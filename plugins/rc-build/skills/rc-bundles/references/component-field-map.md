# Field map — bundle composition objects

Two sources throughout. **DOCS** is the Revenue Lifecycle Management developer guide, v68
PDF, swept 2026-11-24. **PLATFORM** is field metadata from a v68 describe, which is the
same in any org on that API version. Where the two disagree the row says so. A handful of
**ORG** notes record what one org had loaded on 2026-11-25, and are marked as such.

No catalog content appears here, and no org is named: field metadata does not need one.

## Where the guide documents these objects, and where it does not

This matters more here than on any other pair of objects in the model, so it goes first.

`ProductComponentGroup` and `ProductRelatedComponent` have **no object-reference section**
in the v68 guide — no "Represents… Supported Calls… Fields" block of their own. What the
guide gives instead is two much smaller things:

1. **Product Catalog Management Fields on Standard Objects.** This documents exactly one
   field on the group (`ParentGroupId`, API 62.0 and later) and exactly two on the component
   (`ChildProductClassificationId` and `QuoteVisibility`). Nothing else.
2. **The override objects.** `ProductComponentGrpOverride` and `ProductRelComponentOverride`
   do have full field sections, and those sections are the only place the guide describes
   `MinBundleComponents`, `MaxBundleComponents`, `IsExcluded`, `IsComponentRequired`,
   `IsDefaultComponent`, `IsQuantityEditable`, `DoesBundlePriceIncludeChild`,
   `QuantityScaleMethod`, `Quantity`, `MinQuantity` and `MaxQuantity`.

So every behaviour flag a reader needs is documented against the object that *overrides* the
configuration rather than the object that *holds* it. The base-object prose lives in the
Salesforce Object Reference, outside this guide. Treat an override field's description as
the best available DOCS statement of what the base field means, and say so when you cite it.

## ProductComponentGroup

19 fields; 8 of them yours to set. PLATFORM (v68 describe).

| Field | Type | Write | Notes |
|---|---|---|---|
| `Name` | string, required | C+U | writable here, and read-only on the component |
| `Code` | string, nillable | C+U | absent from the guide |
| `Description` | textarea, nillable | C+U | |
| `ParentProductId` | lookup → Product2, required | **C only** | the bundle the group belongs to; cannot be reparented |
| `ParentGroupId` | lookup → ProductComponentGroup, nillable | C+U | the nesting link. DOCS: "the parent product component group in a nested group hierarchy for the same parent product", API 62.0 and later |
| `MinBundleComponents` | int, nillable | C+U | DOCS (on the override): "the minimum number of components that must be added to a group" |
| `MaxBundleComponents` | int, nillable | C+U | DOCS (on the override): "the maximum number of components that can be added to a group" |
| `Sequence` | int, nillable | C+U | display order among sibling groups |
| `CurrencyIsoCode` | picklist, nillable, default USD | C+U | |

`ParentGroupId` is for the *same* parent product per the guide, so a group hierarchy sits
inside one bundle and is not shared between bundles.

## ProductRelatedComponent

30 fields; 14 of them yours to set. PLATFORM (v68 describe).

| Field | Type | Write | Notes |
|---|---|---|---|
| `ParentProductId` | lookup → Product2, required | **C only** | the bundle |
| `ChildProductId` | lookup → Product2, nillable | **C only** | the component |
| `ChildProductClassificationId` | lookup → ProductClassification, nillable | **C only** | DOCS; the alternative to a concrete child |
| `ProductComponentGroupId` | lookup → group, nillable | C+U | which group the component sits in |
| `ProductRelationshipTypeId` | lookup → type, **required** | C+U | what selects Bundle vs Set vs AddOn — see the traps |
| `Quantity` | double, nillable | C+U | DOCS (override): "the default number of child product related components" |
| `MinQuantity` | double, nillable | C+U | DOCS (override): "the minimum quantity for the product component in the product bundle" |
| `MaxQuantity` | double, nillable | C+U | per-component quantity bound, not a component count |
| `IsComponentRequired` | boolean, required, default false | C+U | DOCS (override), "Defaulted on create" |
| `IsDefaultComponent` | boolean, required, default false | C+U | DOCS (override), "Defaulted on create" |
| `IsQuantityEditable` | boolean, required, default false | C+U | DOCS (override), "Defaulted on create" |
| `DoesBundlePriceIncludeChild` | boolean, required, **no default in the org** | C+U | DOCS (override): "indicates whether the bundle price includes the associated child component's price", default false *there* |
| `QuantityScaleMethod` | picklist, nillable, default Proportional | C+U | Constant, Proportional. DOCS (override): "the scaling method that determines how the child product quantity changes as the quantity of the parent product changes in the runtime cart" |
| `QuoteVisibility` | picklist, nillable, default Always | C+U | Always, `Transaction Line Editor Only`, `Quote Document Only`, Never. DOCS |
| `Sequence` | int, nillable | C+U | display order within the group |
| `ParentSellingModelId` | lookup → PSM, nillable | **C only** | absent from the guide |
| `ChildSellingModelId` | lookup → PSM, nillable | **C+U** | absent from the guide; writable where its twin is not |
| `ParentProductRole` | picklist, required | **read-only** | Bundle, Set, AddOn, ProductRequest. **Absent from the guide** |
| `ChildProductRole` | picklist, required | **read-only** | BundleComponent, SetComponent, AddOnComponent, ClassificationComponent, ProductRequestComponent. **Absent from the guide** |
| `UnitOfMeasureId` | lookup → UnitOfMeasure, nillable | **read-only** | |
| `Name` | string | **read-only** | autonumber here; writable on the group |

### The role picklists and their labels

Every value differs from its label on both role picklists, and on the
`ProductRelationshipType` fields they project from. PLATFORM (v68 describe).

| Field | Value | Label |
|---|---|---|
| `ParentProductRole` / `MainProductRoleCat` | `Bundle` | Bundle Parent |
| | `Set` | Set Parent |
| | `AddOn` | **Addon** Parent |
| | `ProductRequest` | Product Request |
| `ChildProductRole` / `AssociatedProductRoleCat` | `BundleComponent` | Bundle Component |
| | `SetComponent` | Set Component |
| | `AddOnComponent` | **Addon** Component |
| | `ClassificationComponent` | **Product** Classification Component |
| | `ProductRequestComponent` | Product Request Component |

Note the capitalisation change on `AddOn` → "Addon", and that
`ClassificationComponent`'s label gains a word the value does not have.

## ProductRelationshipType

13 fields, 4 of them substantive. This is the object that decides the bundle pattern.

| Field | Type | Write | Notes |
|---|---|---|---|
| `Name` | string, required | C+U | |
| `MainProductRoleCat` | picklist, required | **C only** | Bundle, Set, AddOn, ProductRequest. Absent from the guide |
| `AssociatedProductRoleCat` | picklist, nillable | **C only** | the five component roles. DOCS documents this one, with `BundleComponent` and `ClassificationComponent` described and the other three listed |
| `GlobalKey` | string, nillable | C+U | absent from the guide |

Both role categories are **create-only**: a relationship type's pattern cannot be changed
after the record exists. To move a bundle from one pattern to another, point its components
at a different `ProductRelationshipType`.

## The override objects

Both DOCS, both API version 60.0 and later, both requiring Product Catalog Management.

`ProductComponentGrpOverride` carries `ProductComponentGroupId`, `OverrideContextId`
(polymorphic lookup to Product2 — DOCS: "the root bundle product in whose context the group
cardinality is overridden"), `MinBundleComponents`, `MaxBundleComponents` and `IsExcluded`
(DOCS: "excluding a group automatically excludes all child components of the group").

`ProductRelComponentOverride` carries `ProductRelatedComponentId`, `OverrideContextId`
(DOCS: "the ID associated with the root product in a bundle"), `Quantity`, `MinQuantity`,
`MaxQuantity`, `IsComponentRequired`, `IsDefaultComponent`, `IsQuantityEditable`,
`DoesBundlePriceIncludeChild` and `QuantityScaleMethod`.

The mechanism: the same group or component behaves differently depending on which **root**
bundle it is reached through. A sub-bundle reused under two parents can be required in one
and optional in the other without duplicating the component row. Both override objects are
empty in the one org available for checking, so nothing here is observed working.

## Read-only verification queries

Run these against the org being designed for. None of them writes, and none returns
catalog content beyond record ids.

```sql
-- Which bundle patterns does this org actually exercise?
SELECT ParentProductRole, ChildProductRole, COUNT(Id)
FROM ProductRelatedComponent GROUP BY ParentProductRole, ChildProductRole

-- The flag combinations in use, commonest first. This is the catalog's real doctrine.
SELECT IsComponentRequired, IsDefaultComponent, IsQuantityEditable,
       QuantityScaleMethod, DoesBundlePriceIncludeChild, COUNT(Id)
FROM ProductRelatedComponent
GROUP BY IsComponentRequired, IsDefaultComponent, IsQuantityEditable,
         QuantityScaleMethod, DoesBundlePriceIncludeChild
ORDER BY COUNT(Id) DESC

-- Group cardinality: how much of the constraint surface is actually set?
SELECT COUNT(Id) FROM ProductComponentGroup
WHERE MinBundleComponents = null AND MaxBundleComponents = null

-- Nesting, and the containers it implies.
SELECT Id, ParentProductId, ParentGroupId, MinBundleComponents, MaxBundleComponents, Sequence
FROM ProductComponentGroup WHERE ParentGroupId != null

-- Components with no group. The lookup is nillable, so this can be non-zero.
SELECT COUNT(Id) FROM ProductRelatedComponent WHERE ProductComponentGroupId = null

-- Component reuse. Rows far above distinct children means shared sub-bundles.
SELECT ChildProductId, COUNT(Id) FROM ProductRelatedComponent GROUP BY ChildProductId

-- Size distribution: which bundles are big enough to be worth reading by hand?
SELECT ParentProductId, COUNT(Id) FROM ProductRelatedComponent
GROUP BY ParentProductId ORDER BY COUNT(Id) DESC

-- Are there any configuration rules at all?
SELECT COUNT(Id) FROM ProductConfigurationRule

-- Are the override objects in use?
SELECT COUNT(Id) FROM ProductComponentGrpOverride
SELECT COUNT(Id) FROM ProductRelComponentOverride
```
