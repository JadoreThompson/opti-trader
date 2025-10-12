import type { Side } from './side'

export interface TradeEvent {
    price: number
    quantity: number
    side: Side
    executed_at: string
}
