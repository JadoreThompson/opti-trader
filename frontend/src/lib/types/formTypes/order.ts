import { Type, type Static } from '@sinclair/typebox'
import { OrderType } from '../orderType'
import { Side } from '../side'

// ---------- Base ----------
export const OrderBase = Type.Object(
    {
        instrument_id: Type.String(),
        order_type: Type.Enum(OrderType),
        side: Type.Enum(Side),
        quantity: Type.Number({ minimum: 0 }),
    },
    { additionalProperties: true }
)
export type OrderBaseType = Static<typeof OrderBase>

// ---------- Create ----------
export const OrderCreate = Type.Intersect(
    [
        OrderBase,
        Type.Object({
            limit_price: Type.Optional(Type.Number({ minimum: 0 })),
            stop_price: Type.Optional(Type.Number({ minimum: 0 })),
        }),
    ],
    { additionalProperties: false }
)
export type OrderCreateType = Static<typeof OrderCreate>

// ---------- OCO ----------
export const OCOOrderCreate = Type.Object(
    {
        legs: Type.Array(OrderCreate, { minItems: 2, maxItems: 2 }),
    },
    { additionalProperties: false }
)
export type OCOOrderCreateType = Static<typeof OCOOrderCreate>

// ---------- OTO ----------
export const OTOOrderCreate = Type.Object(
    {
        parent: OrderCreate,
        child: OrderCreate,
    },
    { additionalProperties: false }
)
export type OTOOrderCreateType = Static<typeof OTOOrderCreate>

// ---------- OTOCO ----------
export const OTOCOOrderCreate = Type.Object(
    {
        parent: OrderCreate,
        oco_legs: Type.Array(OrderCreate, { minItems: 2, maxItems: 2 }),
    },
    { additionalProperties: false }
)
export type OTOCOOrderCreateType = Static<typeof OTOCOOrderCreate>

// ---------- Modify ----------
export const OrderModify = Type.Object(
    {
        limit_price: Type.Optional(Type.Number({ minimum: 0 })),
        stop_price: Type.Optional(Type.Number({ minimum: 0 })),
    },
    { additionalProperties: false }
)
export type OrderModifyType = Static<typeof OrderModify>

// // ---------- Read ----------
// export const OrderRead = Type.Intersect(
//   [
//     OrderBase,
//     Type.Object({
//       order_id: Type.String({ format: 'uuid' }),
//       user_id: Type.String({ format: 'uuid' }),
//       status: Type.Enum(OrderStatus),
//       executed_quantity: Type.Number(),
//       avg_fill_price: Type.Optional(Type.Number()),
//       created_at: Type.String({ format: 'date-time' }),
//     }),
//   ],
//   { additionalProperties: false }
// )
// export type OrderReadType = Static<typeof OrderRead>

// // ---------- Pagination ----------
// export const PaginatedOrderResponse = Type.Object(
//   {
//     total: Type.Number(),
//     page: Type.Number(),
//     size: Type.Number(),
//     data: Type.Array(OrderRead),
//   },
//   { additionalProperties: false }
// )
// export type PaginatedOrderResponseType = Static<typeof PaginatedOrderResponse>
