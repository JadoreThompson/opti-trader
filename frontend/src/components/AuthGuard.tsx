import useAuthStore from '@/stores/useAuthStore';
import { type FC, type ReactNode, useEffect } from 'react';
import { useNavigate } from 'react-router';

const AuthGuard: FC<{ children: ReactNode }> = ({
    children,
}) => {
    const { isLoggedIn } = useAuthStore()
    const navigate = useNavigate()

    useEffect(() => {
        if (!isLoggedIn) {
            navigate('/login')
        }
    }, [isLoggedIn, navigate])

    if (!isLoggedIn) return null

    return <>{children}</>
}

export default AuthGuard
