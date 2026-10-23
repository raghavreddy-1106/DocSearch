import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Files, 
  Search,
  BarChart2, 
  ListTodo,
  ShieldAlert,
  Settings as SettingsIcon,
  Bell,
  User,
  HelpCircle,
  Lock
} from 'lucide-react';
import clsx from 'clsx';

// Components
import Dashboard from './pages/Dashboard';
import AnalyzeWorkspace from './pages/AnalyzeWorkspace';
import ReviewQueue from './pages/ReviewQueue';
import Landing from './pages/Landing';
import Evaluation from './pages/Evaluation';
import Documents from './pages/Documents';
import Insights from './pages/Insights';
import SettingsPage from './pages/Settings';

import { AppProvider, useApp } from './lib/AppContext';

function Sidebar() {
  const location = useLocation();
  const { documentCount } = useApp();

  const finalNav = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/' },
    { icon: Files, label: 'Documents', path: '/documents' },
    { icon: Search, label: 'Search & Analyze', path: '/analyze', reqDocs: 1 },
    { icon: BarChart2, label: 'Insights', path: '/insights', reqDocs: 1 },
    { icon: ListTodo, label: 'Review Queue', path: '/review' },
    { icon: ShieldAlert, label: 'Evaluation', path: '/evaluation' },
    { icon: SettingsIcon, label: 'Settings', path: '/settings' },
  ];

  return (
    <div className="w-64 bg-surface border-r border-border h-screen flex flex-col fixed left-0 top-0">
      <div className="h-16 flex items-center px-6 border-b border-border">
        <div className="flex items-center gap-2 text-primary-text font-bold text-xl tracking-tight">
          <div className="w-7 h-7 bg-primary-accent rounded-md flex items-center justify-center shadow-sm">
            <Search size={14} className="text-white" />
          </div>
          <span className="text-primary-text">Doc<span className="text-primary-accent">Search</span></span>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto py-6 px-4 flex flex-col gap-1">
        {finalNav.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path;
          const isLocked = item.reqDocs ? documentCount < item.reqDocs : false;
          
          return (
            <Link 
              key={item.path + item.label} 
              to={isLocked ? '/documents' : item.path}
              title={isLocked ? `Upload and index at least ${item.reqDocs} document(s) to enable this feature.` : ''}
              className={clsx(
                "flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 group",
                isLocked 
                  ? "text-gray-400 opacity-60 hover:bg-gray-50 cursor-not-allowed" 
                  : isActive 
                    ? "bg-blue-50 text-primary-accent" 
                    : "text-secondary-text hover:bg-gray-50 hover:text-primary-text"
              )}
            >
              <div className="flex items-center gap-3">
                <Icon size={18} className={isActive ? "text-primary-accent" : "text-gray-400"} />
                {item.label}
              </div>
              {isLocked && <Lock size={12} className="text-gray-300 group-hover:text-gray-400" />}
            </Link>
          );
        })}
      </div>

      <div className="px-4 py-4 border-t border-border">
        <p className="text-[10px] text-gray-400 text-center">DocSearch v1.0 · Document Intelligence</p>
      </div>
    </div>
  );
}

import LiveTopSearchBar from './components/LiveTopSearchBar';
import UserNavDropdown from './components/UserNavDropdown';
import AuthScreen from './components/AuthScreen';
import { AuthProvider, useAuth } from './lib/AuthContext';

function Topnav() {
  return (
    <header className="h-16 bg-surface border-b border-border flex items-center justify-between px-8 sticky top-0 z-20">
      <div className="flex items-center gap-4 flex-1 max-w-xl">
        <LiveTopSearchBar />
      </div>
      <div className="flex items-center gap-4 text-secondary-text">
        <button className="hover:text-primary-text p-1.5 rounded-lg hover:bg-gray-100 transition-colors" title="Notifications">
          <Bell size={18} />
        </button>
        <button className="hover:text-primary-text p-1.5 rounded-lg hover:bg-gray-100 transition-colors" title="Help">
          <HelpCircle size={18} />
        </button>
        <div className="h-5 w-[1px] bg-border mx-1" />
        <UserNavDropdown />
      </div>
    </header>
  );
}

function AppContent() {
  const { isAuthenticated, user } = useAuth();

  // Protect the entire application: usable only after logging in
  if (!isAuthenticated || !user) {
    return <AuthScreen />;
  }

  return (
    <Router>
      <div className="flex min-h-screen bg-background">
        <Sidebar />
        <div className="flex-1 ml-64 flex flex-col">
          <Topnav />
          <main className="flex-1 p-8 overflow-y-auto">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/welcome" element={<Landing />} />
              <Route path="/documents" element={<Documents />} />
              <Route path="/analyze" element={<AnalyzeWorkspace />} />
              <Route path="/review" element={<ReviewQueue />} />
              <Route path="/insights" element={<Insights />} />
              <Route path="/evaluation" element={<Evaluation />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/admin" element={<SettingsPage />} />
              <Route path="*" element={
                <div className="flex flex-col items-center justify-center h-full text-secondary-text">
                  <h2 className="text-xl font-medium text-primary-text mb-2">Module coming soon</h2>
                  <p className="text-sm">This module is currently being scaffolded.</p>
                </div>
              } />
            </Routes>
          </main>
        </div>
      </div>
    </Router>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppProvider>
        <AppContent />
      </AppProvider>
    </AuthProvider>
  );
}

