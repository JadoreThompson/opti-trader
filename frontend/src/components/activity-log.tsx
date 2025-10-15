import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { type FC, useMemo, useState } from "react";

// Icons from lucide-react (assuming installed: npm install lucide-react)
import {
  CheckCircle,
  Clock,
  type LucideIcon,
  PackagePlus,
  XCircle,
} from "lucide-react";

// --- Types Definition ---

type EventType =
  | "order placed"
  | "order cancelled"
  | "order filled"
  | "order partially filled";

interface ActivityEvent {
  id: number;
  eventType: EventType;
  message: string;
  timestamp: string; // ISO string for sorting/display
}

interface EventConfig {
  title: string;
  Icon: LucideIcon;
  colorClass: string; // Tailwind color classes for text and background
}

// --- Mock Initial State ---

const initialEvents: ActivityEvent[] = [
  {
    id: 1,
    eventType: "order placed",
    message: "Limit Buy 100 shares of TSLA @ $180.50 initiated.",
    timestamp: "2023-10-27T10:00:00Z",
  },
  {
    id: 2,
    eventType: "order partially filled",
    message: "50 shares of TSLA filled at $180.50.",
    timestamp: "2023-10-27T10:01:30Z",
  },
  {
    id: 3,
    eventType: "order filled",
    message: "Remaining 50 shares of TSLA filled, order completed.",
    timestamp: "2023-10-27T10:02:15Z",
  },
  {
    id: 4,
    eventType: "order placed",
    message: "Market Sell 50 shares of AAPL executed.",
    timestamp: "2023-10-27T10:05:00Z",
  },
  {
    id: 5,
    eventType: "order cancelled",
    message: "User canceled Limit Sell order for MSFT (200 shares).",
    timestamp: "2023-10-27T10:15:00Z",
  },
  {
    id: 6,
    eventType: "order placed",
    message: "Stop Loss order placed for GOOGL.",
    timestamp: "2023-10-27T10:20:00Z",
  },
];

const ActivityLog: FC = () => {
  // Use state to hold the list of events
  const [events] = useState<ActivityEvent[]>(initialEvents);

  // Configuration map for event styling (icons, colors, titles)
  const eventConfigMap: Record<EventType, EventConfig> = useMemo(
    () => ({
      "order placed": {
        title: "Order Placed",
        Icon: PackagePlus,
        // Blue for initiation
        colorClass: "text-blue-600 bg-blue-50 ",
      },
      "order cancelled": {
        title: "Order Cancelled",
        Icon: XCircle,
        // Red for failure/cancellation
        colorClass: "text-red-600 bg-red-50 ",
      },
      "order filled": {
        title: "Order Filled",
        Icon: CheckCircle,
        // Green for successful completion
        colorClass: "text-green-600 bg-green-50 ",
      },
      "order partially filled": {
        title: "Partial Fill",
        Icon: Clock,
        // Yellow/Amber for pending/in-progress
        colorClass: "text-amber-600 bg-amber-50 ",
      },
    }),
    []
  );

  // Helper function to format timestamp
  const formatTime = (isoString: string) => {
    return new Date(isoString).toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  return (
    <Card className="w-full max-w-lg shadow-lg">
      <CardHeader>
        <CardTitle>Activity Log</CardTitle>
        <CardDescription>Recent trading order updates.</CardDescription>
      </CardHeader>

      {/* Use ScrollArea if the log grows large */}
      <ScrollArea className="h-[300px] px-6 pb-4">
        <CardContent className="p-0 space-y-3">
          {events
            .sort(
              (a, b) =>
                new Date(b.timestamp).getTime() -
                new Date(a.timestamp).getTime()
            ) // Sort newest first
            .map((event) => {
              const config = eventConfigMap[event.eventType];
              const Icon = config.Icon;

              return (
                <div
                  key={event.id}
                  className="w-100 h-15 shadow-sm border-1 mb-1 rounded-md pl-3 py-[0.05rem] pr-[0.05rem] bg-blue-500/20"
                >
                  <div className="w-full h-full bg-white rounded-md p-1">
                    <h4 className="text-xs font-semibold">{config.title}</h4>
                    <span className="text-xs text-muted-foreground">
                      {event.message}
                    </span>
                  </div>
                </div>
              );
            })}
          {events.length === 0 && (
            <p className="text-center text-muted-foreground pt-4">
              No recent activity.
            </p>
          )}
        </CardContent>
      </ScrollArea>
    </Card>
  );
};

export default ActivityLog;
