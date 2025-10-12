import Logo from '@/components/Logo'
import type { FC, ReactNode } from 'react'
import { Link } from 'react-router'

interface AuthLayoutProps {
    children: ReactNode
    title: string
    subtitle: string
    footerText: string
    footerLinkText: string
    footerTo: string
}

const AuthLayout: FC<AuthLayoutProps> = ({
    children,
    title,
    subtitle,
    footerText,
    footerLinkText,
    footerTo,
}) => {
    return (
        <div className="w-full min-h-screen bg-zinc-900 flex items-center justify-center p-4">
            <div className="w-full max-w-md mx-auto">
                <div className="flex justify-center mb-8">
                    <Logo />
                </div>
                <div className="bg-background border border-neutral-800 rounded-lg shadow-xl p-8">
                    <div className="text-center mb-6">
                        <h1 className="text-2xl font-bold text-white mb-1">
                            {title}
                        </h1>
                        <p className="text-muted-foreground text-sm">
                            {subtitle}
                        </p>
                    </div>

                    {children}

                    <p className="mt-6 text-center text-sm text-muted-foreground">
                        {footerText}{' '}
                        <Link
                            to={footerTo}
                            className="font-medium text-primary hover:underline underline-offset-4"
                        >
                            {footerLinkText}
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    )
}

export default AuthLayout
