import type { FC } from 'react'

const MarketSummary: FC<{ ticker: string }> = ({ ticker }) => {
    return (
        <div className="p-4 flex justify-between border-b border-gray-700 text-sm">
            <div>
                <h2 className="text-xl font-bold">{ticker}</h2>
                <p className="text-gray-400">Perpetual Futures</p>
            </div>
            <div className="text-right">
                <p className="text-green-500 text-lg">1234.11</p>
                <p className="text-xs text-gray-400">+2.34% (24h)</p>
            </div>
        </div>
    )
}

export default MarketSummary
