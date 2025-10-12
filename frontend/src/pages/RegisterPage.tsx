import AuthLayout from '@/components/layouts/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { HTTP_BASE_URL } from '@/config'
import useAuthStore from '@/stores/useAuthStore'
import { useEffect, useState, type FC } from 'react'
import { useNavigate } from 'react-router'

const RegisterPage: FC = () => {
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
        const formData = new FormData(e.currentTarget)
        const password = formData.get('password')
        const confirmPassword = formData.get('confirm-password')

        if (password !== confirmPassword) {
            setError('Passwords do not match.')
        } else {
            setError(null)
            await performRegister(formData)
        }
    }

    const performRegister = async (formData: FormData) => {
        const rsp = await fetch(HTTP_BASE_URL + '/auth/register', {
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData),
        })

        if (rsp.ok) {
            setError(null)
            setIsLoggedIn(true)
            navigate('/spot/BTC-USD')
        } else {
            const data = await rsp.json()
            setError(data['error'])
        }
    }

    return (
        <AuthLayout
            title="Create an Account"
            subtitle="Start your trading journey with us today."
            footerText="Already have an account?"
            footerLinkText="Log In"
            footerTo="/login"
        >
            <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                    <label
                        htmlFor="username"
                        className="text-sm font-medium text-muted-foreground"
                    >
                        Username
                    </label>
                    <Input
                        id="username"
                        type="text"
                        placeholder="yourusername"
                        required
                    />
                </div>
                <div className="space-y-2">
                    <label
                        htmlFor="password"
                        className="text-sm font-medium text-muted-foreground"
                    >
                        Password
                    </label>
                    <Input
                        id="password"
                        name="password"
                        type="password"
                        placeholder="*****"
                        required
                    />
                </div>
                <div className="space-y-2">
                    <label
                        htmlFor="confirm-password"
                        className="text-sm font-medium text-muted-foreground"
                    >
                        Confirm Password
                    </label>
                    <Input
                        id="confirm-password"
                        name="confirm-password"
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
                    Create Account
                </Button>
            </form>
        </AuthLayout>
    )
}

export default RegisterPage
