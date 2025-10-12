import { cn } from '@/lib/utils'
import { Bell, User } from 'lucide-react'
import type { FC } from 'react'
import { Link } from 'react-router'
import Logo from './Logo'

const Header: FC = () => {
    return (
        <header className="w-full h-10 z-[999] fixed top-0 left-0 flex justify-between items-center border-b border-b-gray bg-background px-7">
            <div className="flex flex-row gap-2">
                <div className="h-full flex items-center py-2">
                    <Logo
                        frameClassName="w-10 h-6"
                        leftLensClassName="w-3 h-3 left-1"
                        rightLensClassName="w-3 h-3 right-1"
                    />
                </div>
                
            </div>
            <div className="w-fit h-full flex flex-row items-center gap-2 px-2">
                <Link to="#" className="relative ">
                    <Bell
                        className={cn(
                            'size-5 hover:text-blue-300 shake-notification'
                        )}
                    />
                    <div className="w-2 h-2 absolute top-0 right-0 rounded-full bg-red-500"></div>
                </Link>

                <Link to="/user">
                    <User className={cn('size-5 hover:text-blue-300')} />
                </Link>
            </div>
        </header>
    )
}

export default Header
