import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type AuthStoreState = { isLoggedIn: boolean }

type AuthStoreActions = {
    setIsLoggedIn: (isLoggedIn: boolean) => void
}

type AuthStore = AuthStoreState & AuthStoreActions

const useAuthStore = create<AuthStore>()(
    persist(
        (set) => ({
            isLoggedIn: false,
            setIsLoggedIn: (isLoggedIn) => set({ isLoggedIn }),
        }),
        { name: 'auth-storage' }
    )
)

export default useAuthStore
