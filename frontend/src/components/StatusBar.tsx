import { HTTP_BASE_URL } from '@/config'
import type { InstrumentSummary } from '@/lib/types/apiTypes/instrumentSummary'
import { Wifi } from 'lucide-react'
import { useEffect, useRef, useState, type FC } from 'react'

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected'

const StatusBar: FC<{
    connectionStatus: ConnectionStatus
}> = ({ connectionStatus }) => {
    const stylesRef = useRef<CSSStyleDeclaration>(
        getComputedStyle(document.documentElement)
    )

    const [instrumentSummaries, setInstrumentSummaries] = useState<
        InstrumentSummary[]
    >(Array(10).fill({ ticker: 'SOL/USDT', pct: 24.7, price: 1234.11 }))

    useEffect(() => {
        const fetchInstSummaries = async () => {
            const rsp = await fetch(HTTP_BASE_URL + '/instrument/summary', {
                credentials: 'include',
            })
            if (rsp.ok) {
                const data: InstrumentSummary[] = await rsp.json()
                setInstrumentSummaries(data)
            }
        }

        fetchInstSummaries()
    }, [])

    const connectionColor =
        connectionStatus === 'connected'
            ? stylesRef.current.getPropertyValue('--green')
            : connectionStatus === 'connecting'
              ? 'orange'
              : stylesRef.current.getPropertyValue('--red')

    const connectionMsg =
        connectionStatus === 'connected'
            ? 'Connected'
            : connectionStatus === 'connecting'
              ? 'Connecting...'
              : 'Disconnected'

    return (
        <div className="w-full h-full flex items-center relative border-t-1 border-t-gray bg-background text-xs">
            <div className="w-fit h-full absolute top-0 left-0 z-2 flex items-center gap-2 px-2 border-r-1 border-r-gray bg-[var(--background)]">
                <Wifi className="size-3" color={connectionColor} />
                <span style={{ color: connectionColor }}>{connectionMsg}</span>
            </div>
            <div className="w-full h-full flex flex-row">
                <div className="w-fit flex">
                    {instrumentSummaries.map((st) => (
                        <div className="w-50 h-full flex items-center justify-center gap-1 marquee-item">
                            <span className="whitespace-nowrap">
                                {st.instrument}
                            </span>
                            <span
                                className={`${typeof st.change_24h === 'number' ? (st.change_24h < 0 ? 'text-#c93639' : 'text-green-500') : ''}`}
                            >
                                {st.change_24h}%
                            </span>
                            <span className="text-gray-300">{st.price}</span>
                        </div>
                    ))}

                    {instrumentSummaries.map((st) => (
                        <div className="w-50 h-full flex items-center justify-center gap-1 marquee-item">
                            <span className="whitespace-nowrap">
                                {st.instrument}
                            </span>
                            <span
                                className={`${typeof st.change_24h === 'number' ? (st.change_24h < 0 ? 'text-#c93639' : 'text-green-500') : ''}`}
                            >
                                {st.change_24h}%
                            </span>
                            <span className="text-gray-300">{st.price}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}

export default StatusBar
