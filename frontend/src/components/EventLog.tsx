import { EventType } from '@/lib/types/apiTypes/eventType';
import { formatUnderscore } from '@/lib/utils';
import type { FC } from 'react';

export type Log = { event_type: EventType; message: string }

const EventLog: FC<{
    data: Log[]
}> = ({ data }) => {
    const getColor = (eventType: EventType) => {
        switch (eventType) {
            case EventType.ORDER_CANCELLED:
                return 'red'
            case EventType.ORDER_MODIFY_REJECTED:
                return 'red'
            case EventType.ORDER_MODIFIED:
                return 'blue'
            case EventType.ORDER_PARTIALLY_FILLED:
                return 'green'
            case EventType.ORDER_FILLED:
                return 'green'
            case EventType.ORDER_REJECTED:
                return 'red'
            default:
                return 'gray'
        }
    }

    return (
        <div className="w-full min-h-120 max-h-120 flex flex-col gap-3 overflow-y-scroll p-3">
            <h3 className="font-bold mb-2">Activity Log</h3>
            {data.map((val, i) => (
                <div
                    key={i}
                    className="w-full h-10 flex items-center border-l-2 pl-2"
                    style={{ borderLeftColor: getColor(val.event_type) }}
                >
                    <div className="flex flex-col">
                        <span className="text-sm font-bold">
                            {formatUnderscore(val.event_type)}
                        </span>
                        <span className="text-xs text-neutral-500 whitespace-nowrap">
                            {val.message}
                        </span>
                    </div>
                </div>
            ))}
        </div>
    )
}

export default EventLog
