import { BrowserRouter, Route, Routes } from 'react-router'
import AuthGuard from './components/AuthGuard'
import InstrumentCreatePage from './pages/InstrumentCreatePage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import TradingPage from './pages/TradingPage'
import UserOverviewPage from './pages/UserOverviewPage'

function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route
                    path="/register"
                    element={<AuthGuard children={<RegisterPage />} />}
                />
                <Route
                    path="/login"
                    element={<AuthGuard children={<LoginPage />} />}
                />
                <Route
                    path="/user"
                    element={<AuthGuard children={<UserOverviewPage />} />}
                />
                <Route
                    path="/spot/:instrument"
                    element={<AuthGuard children={<TradingPage />} />}
                />
                <Route
                    path="/instrument"
                    element={<AuthGuard children={<InstrumentCreatePage />} />}
                />
            </Routes>
        </BrowserRouter>
    )
}

export default App
