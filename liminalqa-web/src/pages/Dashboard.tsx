import { useEffect, useState } from 'react';
import DriftChart from '../components/DriftChart';
import ProtocolCard from '../components/ProtocolCard';
import { ArrowUpRight, CheckCircle, Clock, AlertTriangle } from 'lucide-react';
import axios from 'axios';

// Mock data until API is connected
const MOCK_METRICS = {
  totalTests: 12450,
  passRate: 98.2,
  avgDuration: 342,
  activeFlakes: 3
};

export default function Dashboard() {
  const [metrics, setMetrics] = useState(MOCK_METRICS);

  // Example of fetching data (will fail if API not running, so keep mock for UI dev)
  useEffect(() => {
    // axios.get('/api/metrics').then(res => setMetrics(res.data)).catch(console.error);
  }, []);

  return (
    <div className="space-y-6">
      {/* KPI Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KpiCard
          title="Total Tests"
          value={metrics.totalTests.toLocaleString()}
          change="+12%"
          icon={<CheckCircle className="text-emerald-400" />}
        />
        <KpiCard
          title="Pass Rate"
          value={`${metrics.passRate}%`}
          change="+0.5%"
          icon={<ArrowUpRight className="text-cyan-400" />}
        />
        <KpiCard
          title="Avg Duration"
          value={`${metrics.avgDuration}ms`}
          change="-12ms"
          icon={<Clock className="text-violet-400" />}
        />
        <KpiCard
          title="Active Flakes"
          value={metrics.activeFlakes}
          change="0"
          icon={<AlertTriangle className="text-amber-400" />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Chart */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-semibold text-slate-200">Baseline Drift (7 Days)</h3>
            <select className="bg-slate-800 border-none text-slate-400 text-sm rounded-lg">
              <option>Authentication Suite</option>
              <option>Payment Gateway</option>
            </select>
          </div>
          <div className="h-80 w-full">
            <DriftChart />
          </div>
        </div>

        {/* Protocol Resonance */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-slate-200 mb-6">Protocol Resonance</h3>
          <ProtocolCard />
        </div>
      </div>
    </div>
  );
}

function KpiCard({ title, value, change, icon }: { title: string, value: string | number, change: string, icon: React.ReactNode }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 hover:border-slate-700 transition-colors">
      <div className="flex justify-between items-start mb-4">
        <div className="p-2 bg-slate-800/50 rounded-lg">{icon}</div>
        <span className={`text-xs font-medium px-2 py-1 rounded-full ${change.startsWith('+') ? 'bg-emerald-900/30 text-emerald-400' : 'bg-slate-800 text-slate-400'}`}>
          {change}
        </span>
      </div>
      <h3 className="text-slate-400 text-sm font-medium">{title}</h3>
      <p className="text-2xl font-bold text-slate-100 mt-1">{value}</p>
    </div>
  );
}
