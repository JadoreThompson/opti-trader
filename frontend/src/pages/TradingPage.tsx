import type { FC } from "react";

const TradingPage: FC = () => {
  return (
    <>
      <header className="z-[2] h-10 w-full fixed top-0 left-0 bg-white">
        Header
      </header>
      <main className="grid grid-cols-4 ro mt-10 pb-5 bg-gray-700">
        <div className="h-full col-span-3 bg-red-100">
          <div className="h-15 w-full flex bg-green-500">a</div>
          <div className="h-120 w-3/4 bg-pink-500">a</div>
          <div className="h-120 flex-1 bg-blue-500">a</div>
        </div>
        <div className="h-full col-span-1 flex flex-col bg-red-500">
          <div className="h-120 w-full mb-1 bg-blue-200"></div>
          <div className="h-120 w-full bg-blue-200"></div>
        </div>
      </main>
    </>
  );
};
export default TradingPage;
