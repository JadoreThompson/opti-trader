import { useRef, type FC } from 'react';

export type PriceLevel = { price: number; quantity: number }

interface OrderBookProps {
    asks?: PriceLevel[]
    bids?: PriceLevel[]
}

const OrderBook: FC<OrderBookProps> = ({ asks = [], bids = [] }) => {
    const maxAskSize = Math.max(...asks.map((ask) => ask.quantity))

    const maxBidSize = Math.max(...bids.map((bid) => bid.quantity))

    const stylesRef = useRef<CSSStyleDeclaration>(
        getComputedStyle(document.documentElement)
    )

    return (
        <div className="w-full h-full text-sm">
            <h2 className="mb-2 font-semibold p-4">Order Book</h2>
            <div className="w-full flex flex-row">
                <div className="w-full h-full flex flex-col">
                    <div className="flex justify-between px-3">
                        <span className="text-xs font-bold text-gray-500">
                            SIZE
                        </span>
                        <span className="text-xs font-bold text-gray-500">
                            BID PRICE
                        </span>
                    </div>
                    <div className="w-full">
                        {bids.map((bid, idx) => (
                            <div
                                key={`bid-${idx}`}
                                className={`w-full h-[20px] relative flex flex-row-reverse text-[var(--green)] text-xs`}
                            >
                                <div className="w-full h-full z-2 absolute top-0 left-0 flex justify-between items-center px-3">
                                    <span>{bid.quantity}</span>
                                    <span>{bid.price.toFixed(2)}</span>
                                </div>
                                <div
                                    className="h-full flex bg-green-500/20"
                                    style={{
                                        width: `${Math.round(100 * (bid.quantity / maxBidSize))}%`,
                                    }}
                                ></div>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="w-full h-full flex flex-col">
                    <div className="flex justify-between px-3">
                        <span className="text-xs font-bold text-gray-500">
                            ASK PRICE
                        </span>
                        <span className="text-xs font-bold text-gray-500">
                            SIZE
                        </span>
                    </div>
                    <div className="w-full ">
                        {asks.map((ask, idx) => (
                            <div
                                key={`ask-${idx}`}
                                className="w-full h-[20px] relative flex text-xs"
                                style={{
                                    color: stylesRef.current.getPropertyValue(
                                        '--red'
                                    ),
                                }}
                            >
                                <div className="w-full h-full z-2 absolute top-0 left-0 flex items-center justify-between px-3">
                                    <span>{ask.price.toFixed(2)}</span>
                                    <span>{ask.quantity}</span>
                                </div>
                                <div
                                    className="h-full flex"
                                    style={{
                                        backgroundColor: '#c3201f',
                                        opacity: 0.1,
                                        width: `${Math.round(100 * (ask.quantity / maxAskSize))}%`,
                                    }}
                                ></div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    )
}

export default OrderBook
