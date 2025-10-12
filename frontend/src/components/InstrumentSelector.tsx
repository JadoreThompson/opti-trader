import { HTTP_BASE_URL } from '@/config'
import { cn } from '@/lib/utils'
import { Search } from 'lucide-react'
import { type FC, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate } from 'react-router'
import { Input } from './ui/input'

interface InstrumentListItem {
    instrument_id: string
    price?: number
    h24_change?: number
}

interface InstrumentSelectorProps {
    isOpen: boolean
    onClose: () => void
    onSelect: (instrumentId: string) => void
    triggerRef: React.RefObject<HTMLElement>
}

const InstrumentSelector: FC<InstrumentSelectorProps> = ({
    isOpen,
    onClose,
    onSelect,
    triggerRef,
}) => {
    const navigate = useNavigate()
    const [instruments, setInstruments] = useState<InstrumentListItem[]>([])
    const [searchTerm, setSearchTerm] = useState('')
    const [isLoading, setIsLoading] = useState(true)
    const popoverRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        const fetchInstruments = async () => {
            setIsLoading(true)
            try {
                const rsp = await fetch(`${HTTP_BASE_URL}/instruments`)

                if (rsp.ok) {
                    const data: InstrumentListItem[] = await rsp.json()
                    setInstruments(data)
                } else {
                    console.error('Failed to fetch instruments')
                }
            } catch (error) {
                console.error('Error fetching instruments:', error)
            } finally {
                setIsLoading(false)
            }
        }

        if (isOpen) {
            fetchInstruments()
        }
    }, [isOpen])

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            const target = event.target
            if (!popoverRef.current?.contains(target)) {
                onClose()
            }
        }

        document.addEventListener('mousedown', handleClickOutside)

        return () => {
            document.removeEventListener('mousedown', handleClickOutside)
        }
    }, [isOpen, onClose, triggerRef])

    const filteredInstruments = instruments.filter((inst) =>
        inst.instrument_id.toLowerCase().includes(searchTerm.toLowerCase())
    )

    const handleSelect = (instrumentId: string) => {
        onSelect(instrumentId)
        onClose()
    }

    if (!isOpen) {
        return null
    }

    const triggerRect = triggerRef.current?.getBoundingClientRect()
    const style = triggerRect
        ? {
              top: `${triggerRect.bottom + 8}px`,
              left: `${triggerRect.left}px`,
          }
        : {}

    return createPortal(
        <div
            ref={popoverRef}
            style={style}
            className="absolute z-50 w-[450px] h-[500px] bg-background border border-neutral-800 rounded-md shadow-lg flex flex-col p-4"
        >
            <div className="w-full flex justify-between mb-1">
                <h3 className="text-lg font-semibold mb-3">Select Market</h3>
                <Link
                    to="/instrument/"
                    className="h-fit p-1 rounded-sm font-semibold bg-background text-white hover:bg-neutral-800 cursor-pointer"
                >
                    Create Coin
                </Link>
            </div>
            <div className="relative mb-3">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                <Input
                    type="text"
                    placeholder="Search instrument"
                    className="pl-9"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                />
            </div>

            <div className="grid grid-cols-3 gap-4 px-3 py-2 text-xs text-muted-foreground font-medium border-b border-neutral-800">
                <span>Pair</span>
                <span className="text-right">Last Price</span>
                <span className="text-right">24h Change</span>
            </div>

            <div className="flex-1 overflow-y-auto">
                {isLoading ? (
                    <div className="flex justify-center items-center h-full text-muted-foreground">
                        Loading...
                    </div>
                ) : (
                    filteredInstruments.map((inst) => (
                        <div
                            key={inst.instrument_id}
                            onClick={() => handleSelect(inst.instrument_id)}
                            className="grid grid-cols-3 gap-4 px-3 py-3 text-sm hover:bg-neutral-800 cursor-pointer rounded-md"
                        >
                            <span>{inst.instrument_id}</span>
                            <span className="text-right">
                                {inst.price?.toFixed(2) ?? '-'}
                            </span>
                            <span
                                className={cn('text-right', {
                                    'text-[var(--green)]':
                                        (inst.h24_change ?? 0) >= 0,
                                    'text-[var(--red)]':
                                        (inst.h24_change ?? 0) < 0,
                                })}
                            >
                                {inst.h24_change?.toFixed(2) ?? '-'}%
                            </span>
                        </div>
                    ))
                )}
            </div>
        </div>,
        document.body
    )
}

export default InstrumentSelector
