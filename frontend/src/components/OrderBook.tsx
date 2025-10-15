import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { type FC, useMemo, useState } from "react";

interface OrderBookEntry {
  price: number;
  quantity: number; // Volume at this price level
  cumulative: number; // Running total of quantity
}

type OrderBookSide = "bid" | "ask";

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
};

const formatQuantity = (quantity: number) => {
  return quantity.toLocaleString("en-US", { maximumFractionDigits: 4 });
};

const generateOrderBookData = (
  isBid: boolean,
  basePrice: number,
  count: number
): OrderBookEntry[] => {
  const data: { price: number; quantity: number }[] = [];
  let currentPrice = basePrice;

  for (let i = 0; i < count; i++) {
    const quantity = Math.floor(Math.random() * 50) + 10;
    const priceChange = Math.random() * 0.05 + 0.01; // Small random price fluctuation

    if (isBid) {
      // Bids: Price decreases from the base price
      currentPrice -= priceChange;
    } else {
      // Asks: Price increases from the base price
      currentPrice += priceChange;
    }

    data.push({
      price: currentPrice,
      quantity: quantity,
      cumulative: 0,
    });
  }

  data.sort((a, b) => (isBid ? b.price - a.price : a.price - b.price));

  let cumulative = 0;
  const processedData: OrderBookEntry[] = data.map((entry) => {
    cumulative += entry.quantity;
    return { ...entry, cumulative };
  });

  return processedData;
};

interface OrderBookRowProps {
  entry: OrderBookEntry;
  side: OrderBookSide;
  depthPercentage: number;
}

const OrderBookRow: FC<OrderBookRowProps> = ({
  entry,
  side,
  depthPercentage,
}) => {
  const isBid = side === "bid";
  const depthBarColor = isBid
    ? "bg-green-500/30 group-hover:bg-green-500/50"
    : "bg-red-500/30 group-hover:bg-red-500/50";
  const priceColor = isBid ? "text-green-500" : "text-red-500";
  const alignment = isBid ? "left" : "right";

  return (
    <div
      className="relative text-xs h-6 px-3 py-1 grid grid-cols-[1fr_1fr_1fr] transition-colors group"
      role="row"
    >
      <div
        className={cn(
          "absolute inset-0 z-0 transition-width duration-300",
          depthBarColor
        )}
        style={{
          width: `${depthPercentage}%`,

          [alignment]: 0,
        }}
      />

      <div className="z-10 text-left text-muted-foreground hidden sm:block">
        {formatQuantity(entry.cumulative)}
      </div>

      <div className="z-10 text-right text-foreground">
        {formatQuantity(entry.quantity)}
      </div>

      <div className={cn("z-10 text-right font-medium", priceColor)}>
        {formatPrice(entry.price)}
      </div>
    </div>
  );
};

const OrderBook: FC = () => {
  const [spreadPrice] = useState(30500.0);
  const [numLevels] = useState(15);

  const bids = useMemo(
    () => generateOrderBookData(true, spreadPrice * 0.999, numLevels),
    [spreadPrice, numLevels]
  );
  const asks = useMemo(
    () => generateOrderBookData(false, spreadPrice * 1.001, numLevels),
    [spreadPrice, numLevels]
  );

  const maxBidCumulative = bids[bids.length - 1]?.cumulative || 1;
  const maxAskCumulative = asks[asks.length - 1]?.cumulative || 1;

  const maxDepth = Math.max(maxBidCumulative, maxAskCumulative, 1);

  const bestAsk = asks[0]?.price || spreadPrice;
  const bestBid = bids[0]?.price || spreadPrice;
  const spread = bestAsk - bestBid;

  const renderHeader = () => (
    <div className="text-xs text-muted-foreground font-medium sticky top-0 bg-background/95 backdrop-blur-sm z-20 grid grid-cols-[1fr_1fr_1fr] border-b pb-1 px-3">
      <div className="text-left hidden sm:block">Cumulative</div>
      <div className="text-right">Quantity</div>
      <div className="text-right">Price (USD)</div>
    </div>
  );

  const renderSide = (data: OrderBookEntry[], side: OrderBookSide) =>
    data.map((entry) => (
      <OrderBookRow
        key={entry.price}
        entry={entry}
        side={side}
        depthPercentage={(entry.cumulative / maxDepth) * 100}
      />
    ));

  return (
    <Card className="w-full max-w-md shadow-xl border">
      <CardHeader>
        <CardTitle>Order Book (BTC/USD)</CardTitle>
      </CardHeader>

      <CardContent className="p-0">
        <div className="space-y-1">
          <ScrollArea className="h-[250px] relative">
            {renderHeader()}
            <div className="flex flex-col-reverse">
              {renderSide(asks, "ask")}
            </div>
          </ScrollArea>

          <ScrollArea className="h-[250px] relative">
            <div className="flex flex-col">{renderSide(bids, "bid")}</div>
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  );
};

export default OrderBook;
