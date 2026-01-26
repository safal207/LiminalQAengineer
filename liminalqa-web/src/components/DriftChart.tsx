import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const data = [
  { name: 'Mon', value: 340, baseline: 320 },
  { name: 'Tue', value: 338, baseline: 320 },
  { name: 'Wed', value: 345, baseline: 320 },
  { name: 'Thu', value: 360, baseline: 320 },
  { name: 'Fri', value: 355, baseline: 320 },
  { name: 'Sat', value: 380, baseline: 320 },
  { name: 'Sun', value: 395, baseline: 320 },
];

export default function DriftChart() {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.3}/>
            <stop offset="95%" stopColor="#22d3ee" stopOpacity={0}/>
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis dataKey="name" stroke="#94a3b8" tick={{fontSize: 12}} />
        <YAxis stroke="#94a3b8" tick={{fontSize: 12}} />
        <Tooltip
          contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', color: '#f8fafc' }}
          itemStyle={{ color: '#22d3ee' }}
        />
        <Area type="monotone" dataKey="value" stroke="#22d3ee" strokeWidth={2} fillOpacity={1} fill="url(#colorValue)" />
        <Area type="monotone" dataKey="baseline" stroke="#64748b" strokeWidth={2} strokeDasharray="5 5" fill="none" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
