import React, { useState, useRef, useEffect } from 'react';
import { 
  User, 
  LogOut, 
  ChevronDown, 
  Settings,
  ShieldCheck,
  Activity
} from 'lucide-react';
import clsx from 'clsx';
import { useAuth } from '../lib/AuthContext';
import { useNavigate } from 'react-router-dom';

export default function UserNavDropdown() {
  const { user, isAuthenticated, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (!isAuthenticated || !user) {
    return null;
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2.5 p-1 pl-1.5 pr-2.5 rounded-full border border-border bg-white hover:bg-gray-50 transition-all shadow-sm group cursor-pointer"
      >
        <div 
          className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold shadow-sm"
          style={{ backgroundColor: user.avatar_color || '#3B82F6' }}
        >
          {user.name.charAt(0).toUpperCase()}
        </div>
        <div className="text-left hidden sm:block">
          <p className="text-xs font-semibold text-primary-text leading-tight group-hover:text-primary-accent">
            {user.name.split(' ')[0]}
          </p>
          <p className="text-[10px] text-secondary-text leading-none mt-0.5 truncate max-w-[100px]">
            {user.title || user.email}
          </p>
        </div>
        <ChevronDown size={12} className={clsx("text-gray-400 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-64 bg-white border border-border rounded-xl shadow-2xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
          {/* User Info Header */}
          <div className="p-4 border-b border-border bg-gradient-to-r from-gray-50 to-blue-50/40">
            <div className="flex items-center gap-3">
              <div 
                className="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm font-bold shadow-md flex-shrink-0"
                style={{ backgroundColor: user.avatar_color || '#3B82F6' }}
              >
                {user.name.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold text-primary-text truncate">{user.name}</p>
                <p className="text-[11px] text-secondary-text truncate">{user.email}</p>
                <div className="mt-1.5 flex items-center gap-1.5">
                  <span className="text-[9px] font-bold px-2 py-0.5 rounded-full border border-blue-200 bg-blue-50 text-blue-700 tracking-wider">
                    {user.title || 'Personal Account'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Links */}
          <div className="p-1.5">
            <button
              onClick={() => {
                navigate('/insights');
                setOpen(false);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-secondary-text hover:text-primary-text hover:bg-gray-50 rounded-lg transition-colors cursor-pointer"
            >
              <Activity size={14} className="text-blue-500" />
              <span>My Search Activity & Stats</span>
            </button>

            <button
              onClick={() => {
                navigate('/settings');
                setOpen(false);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-secondary-text hover:text-primary-text hover:bg-gray-50 rounded-lg transition-colors cursor-pointer"
            >
              <Settings size={14} className="text-gray-400" />
              <span>Workspace Settings</span>
            </button>

            <div className="my-1 border-t border-border" />

            <button
              onClick={() => {
                logout();
                setOpen(false);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-red-600 hover:bg-red-50 rounded-lg transition-colors cursor-pointer"
            >
              <LogOut size={14} className="text-red-500" />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
