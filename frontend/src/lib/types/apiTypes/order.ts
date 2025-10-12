import type { OrderStatus } from '../orderStatus'
import type { OrderType } from '../orderType'

export interface Order {
    order_id: string
    instrument_id: string
    side: string
    order_type: OrderType
    price: number | null
    limit_price: number | null
    stop_price: number | null
    avg_fill_price: number | null
    status: OrderStatus
    quantity: number
    executed_quantity: number
    created_at: string
}
