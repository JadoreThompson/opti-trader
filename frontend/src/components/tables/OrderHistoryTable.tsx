import type { OrderTableProps } from '@/lib/props/tableProps.'
import { Side } from '@/lib/types/side'
import { formatUnderscore } from '@/lib/utils'
import { useEffect, useRef, type FC } from 'react'

const OrderHistory: FC<OrderTableProps> = ({ orders, onScrollEnd }) => {
    const tableBottomRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    onScrollEnd()
                }
            })
        })

        if (tableBottomRef.current) {
            observer.observe(tableBottomRef.current)
        }

        return () => {
            if (tableBottomRef.current) {
                observer.disconnect()
            }
        }
    }, [])

    return (
        <>
            <div className="w-full h-full overflow-auto">
                <table className="min-w-full text-sm text-left border-collapse">
                    <thead className="text-sm font-semibold">
                        <tr className="text-neutral-500">
                            <th>Symbol</th>
                            <th>Quantity</th>
                            <th>Side</th>
                            <th>Type</th>
                            <th>Filled Price</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {orders.map((order, idx) => (
                            <tr
                                key={order.order_id}
                                className={`h-10 ${idx > 0 ? 'border-t' : ''}`}
                            >
                                <td>{order.instrument_id}</td>
                                <td>{order.quantity}</td>
                                <td>
                                    {order.side === Side.BID ? 'Buy' : 'Sell'}
                                </td>
                                <td>
                                    {order.order_type.charAt(0).toUpperCase() +
                                        order.order_type.slice(1)}
                                </td>

                                <td
                                    className={
                                        order.avg_fill_price == null
                                            ? 'text-gray-500'
                                            : ''
                                    }
                                >
                                    {order.avg_fill_price ?? '--'}
                                </td>
                                
                                <td>{formatUnderscore(order.status)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                <div ref={tableBottomRef} />
            </div>
        </>
    )
}

export default OrderHistory
