import AuthLayout from '@/components/layouts/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { HTTP_BASE_URL } from '@/config'
import useAuthStore from '@/stores/useAuthStore'
import { useEffect, useState, type FC } from 'react'
import { Link, useNavigate } from 'react-router'

const LoginPage: FC = () => {
    const navigate = useNavigate()
    const { setIsLoggedIn } = useAuthStore()
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        const checkIsLoggedIn = async () => {
            const rsp = await fetch(HTTP_BASE_URL + '/auth/me', {
                credentials: 'include',
            })
            if (rsp.ok) {
                navigate('/spot/BTC-USD')
            }
        }
        checkIsLoggedIn()
    }, [])

    const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault()
        setError('Invalid credentials. Please try again.')

        const rsp = await fetch(HTTP_BASE_URL + '/auth/login', {
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(new FormData(e.currentTarget)),
        })

        if (rsp.ok) {
            setError(null)
            setIsLoggedIn(true)
            navigate('/spot/BTC-USD')
        }

        const data = await rsp.json()
        setError(data['error'])
    }

    return (
        <AuthLayout
            title="Welcome Back"
            subtitle="Enter your credentials to access your account."
            footerText="Don't have an account?"
            footerLinkText="Sign Up"
            footerTo="/register"
        >
            <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                    <label
                        htmlFor="email"
                        className="text-sm font-medium text-muted-foreground"
                    >
                        Email or Username
                    </label>
                    <Input
                        id="email"
                        type="email"
                        placeholder="name@example.com"
                        required
                    />
                </div>
                <div className="space-y-2">
                    <div className="flex items-center justify-between">
                        <label
                            htmlFor="password"
                            className="text-sm font-medium text-muted-foreground"
                        >
                            Password
                        </label>
                        <Link
                            to="/forgot-password"
                            className="text-sm font-medium text-primary hover:underline underline-offset-4"
                        >
                            Forgot Password?
                        </Link>
                    </div>
                    <Input
                        id="password"
                        type="password"
                        placeholder="*****"
                        required
                    />
                </div>

                {error && (
                    <div className="text-center text-red-500 text-sm p-2 bg-red-500/10 rounded-md">
                        {error}
                    </div>
                )}

                <Button type="submit" className="w-full">
                    Log In
                </Button>
            </form>
        </AuthLayout>
    )
}

export default LoginPage
