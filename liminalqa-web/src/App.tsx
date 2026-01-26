import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import { Activity, LayoutDashboard, Database, Zap } from 'lucide-react';

function App() {
  return (
    <Router>
      <div className="flex h-screen bg-slate-950 text-slate-100 font-sans">
        {/* Sidebar */}
        <aside className="w-64 bg-slate-900 border-r border-slate-800">
          <div className="p-6 border-b border-slate-800">
            <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              LiminalQA
            </h1>
            <p className="text-xs text-slate-500 mt-1">Resonance Engine v0.4</p>
          </div>

          <nav className="p-4 space-y-2">
            <NavLink to="/" icon={<LayoutDashboard size={20} />} label="Dashboard" />
            <NavLink to="/tests" icon={<Activity size={20} />} label="Test Explorer" />
            <NavLink to="/drift" icon={<Zap size={20} />} label="Drift Analysis" />
            <NavLink to="/data" icon={<Database size={20} />} label="Data & Schema" />
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-auto bg-slate-950">
          <header className="h-16 border-b border-slate-800 flex items-center px-8 bg-slate-900/50 backdrop-blur">
            <h2 className="text-lg font-medium text-slate-200">System Resonance</h2>
          </header>

          <div className="p-8">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/tests" element={<div className="text-slate-500">Test Explorer Module (Coming Soon)</div>} />
              <Route path="/drift" element={<div className="text-slate-500">Drift Analysis Module (Coming Soon)</div>} />
              <Route path="/data" element={<div className="text-slate-500">Data Module (Coming Soon)</div>} />
            </Routes>
          </div>
        </main>
      </div>
    </Router>
  );
}

function NavLink({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <Link to={to} className="flex items-center gap-3 px-4 py-3 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-slate-800/50 transition-colors">
      {icon}
      <span className="font-medium">{label}</span>
    </Link>
  );
}

export default App;
