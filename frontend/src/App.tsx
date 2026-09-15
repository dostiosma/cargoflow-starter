import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { Login } from '@/components/Login'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { Layout } from '@/components/Layout'
import { Dashboard } from '@/pages/Dashboard'
import { OrdersList } from '@/pages/OrdersList'
import { CreateOrder } from '@/pages/CreateOrder'
import { OrderDetail } from '@/pages/OrderDetail'
import { Fleet } from '@/pages/Fleet'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="orders" element={<OrdersList />} />
            <Route path="orders/new" element={<CreateOrder />} />
            <Route path="orders/:id" element={<OrderDetail />} />
            <Route path="fleet" element={<Fleet />} />
          </Route>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
