import type { FC } from 'react'

interface LogoProps {
    frameClassName?: string
    leftLensClassName?: string
    rightLensClassName?: string
}

const Logo: FC<LogoProps> = ({
    frameClassName = 'w-75 h-35',
    leftLensClassName = 'w-27 h-27 top-5 left-5',
    rightLensClassName = 'w-27 h-27 top-5 right-5',
}) => {
    return (
        <div className={`relative flex items-center ${frameClassName}`}>
            <div
                className="w-full h-full rounded-lg bg-[#010311]"
                style={{
                    clipPath:
                        'polygon(0% 0%, 40% 0%, 45% 5%, 55% 5%, 60% 0%, 100% 0%, 100% 50%, 90% 100%, 60% 100%, 52% 40%, 47% 40%, 40% 100%, 10% 100%, 0% 50%)',
                }}
            ></div>
            {/* Left Lens */}
            <div
                className={`absolute z-[2] bg-white/5 ${leftLensClassName}`}
                style={{
                    clipPath:
                        'polygon(0% 0%, 85% 0%, 95% 5.5%, 100% 30%, 80% 100%, 22% 100%, 0% 50%)',
                }}
            >
                <div className="w-10 h-100 rotate-45 absolute shiner top-10 bg-white/5"></div>
            </div>
            {/* Right Lens */}
            <div
                className={`absolute z-[2] bg-white/5 ${rightLensClassName}`}
                style={{
                    clipPath:
                        'polygon(100% 0%, 15% 0%, 5% 5.5%, 0% 30%, 20% 100%, 78% 100%, 100% 50%)',
                }}
            ></div>
        </div>
    )
}

export default Logo
