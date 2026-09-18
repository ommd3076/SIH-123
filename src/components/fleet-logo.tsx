'use client';

import React from 'react';

interface FleetLogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  showSubtitle?: boolean;
}

export function FleetLogo({ className = '', size = 'md', showSubtitle = true }: FleetLogoProps) {
  const iconSizes = {
    sm: 'w-7 h-7',
    md: 'w-8 h-8',
    lg: 'w-10 h-10',
  };

  const textSizes = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-xl',
  };

  return (
    <div className={`flex items-center gap-2.5 select-none ${className}`}>
      {/* Dynamic Graph/AMR Icon */}
      <div className={`relative ${iconSizes[size]} flex items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 via-orange-600 to-red-600 shadow-md shadow-orange-500/20 text-white`}>
        <svg
          viewBox="0 0 28 28"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="w-5 h-5 text-white drop-shadow-sm"
        >
          {/* Outer Mesh Lines */}
          <path
            d="M14 3L24 8.5V19.5L14 25L4 19.5V8.5L14 3Z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
            className="opacity-70"
          />
          {/* Inner Coordination Nodes */}
          <circle cx="14" cy="14" r="2.8" fill="currentColor" />
          <circle cx="14" cy="6" r="1.6" fill="currentColor" />
          <circle cx="21.5" cy="10" r="1.6" fill="currentColor" />
          <circle cx="21.5" cy="18" r="1.6" fill="currentColor" />
          <circle cx="14" cy="22" r="1.6" fill="currentColor" />
          <circle cx="6.5" cy="18" r="1.6" fill="currentColor" />
          <circle cx="6.5" cy="10" r="1.6" fill="currentColor" />
          {/* Predictive Vectors */}
          <path d="M14 6L14 11.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M21.5 10L16.5 12.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M21.5 18L16.5 15.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M14 22L14 16.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M6.5 18L11.5 15.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M6.5 10L11.5 12.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500 border border-white"></span>
        </span>
      </div>

      {/* Brand Typography */}
      <div className="flex flex-col text-left">
        <div className="flex items-center gap-1.5 leading-tight">
          <span className={`font-bold tracking-tight text-slate-900 ${textSizes[size]}`}>
            Fleet<span className="text-orange-600">Graph</span>
          </span>
          <span className="font-mono text-[9px] font-semibold bg-orange-50 text-orange-700 border border-orange-200/80 px-1 py-0.5 rounded tracking-wide uppercase shadow-2xs">
            Edge-AI
          </span>
        </div>
        {showSubtitle && (
          <span className="text-[10px] font-mono text-slate-500 tracking-tight leading-none mt-0.5">
            Distributed AMR Fleet Grid
          </span>
        )}
      </div>
    </div>
  );
}