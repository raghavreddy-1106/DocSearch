import React from 'react';
import { Shield, Search, LineChart, FileText, Lock, CheckCircle2 } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function Landing() {
  return (
    <div className="min-h-screen bg-background font-sans text-primary-text flex flex-col">
      {/* Navigation */}
      <nav className="border-b border-border bg-surface sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-2 font-bold text-2xl tracking-tight text-primary-text">
            <div className="w-8 h-8 bg-primary-accent rounded-md flex items-center justify-center shadow-sm">
              <Search size={16} className="text-white" />
            </div>
            <span>Doc<span className="text-primary-accent">Search</span></span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#features" className="text-sm font-medium text-secondary-text hover:text-primary-text transition-colors">Features</a>
            <a href="#security" className="text-sm font-medium text-secondary-text hover:text-primary-text transition-colors">Security</a>
            <div className="h-5 w-px bg-border"></div>
            <Link to="/" className="text-sm font-medium text-primary-text hover:text-primary-accent transition-colors">Sign In</Link>
            <Link to="/" className="bg-primary-accent text-white px-5 py-2.5 rounded-md text-sm font-medium hover:bg-blue-600 transition-colors shadow-sm">
              Request Demo
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="py-24 px-6">
        <div className="max-w-5xl mx-auto text-center flex flex-col items-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 border border-blue-100 text-primary-accent text-xs font-bold uppercase tracking-wider mb-8">
            <Shield size={14} /> Enterprise Document Intelligence
          </div>
          
          <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight text-primary-text leading-[1.1] mb-6">
            Search Every Page.<br /><span className="text-primary-accent">Understand Every Document.</span>
          </h1>
          
          <p className="text-lg md:text-xl text-secondary-text max-w-3xl mb-10 leading-relaxed">
            DocSearch finds exact matches across every page, retrieves real evidence, and delivers AI-powered answers grounded in your actual documents.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center gap-4 w-full sm:w-auto">
            <Link to="/" className="w-full sm:w-auto bg-primary-text text-white px-8 py-3.5 rounded-md text-base font-medium hover:bg-gray-800 transition-colors shadow-md flex items-center justify-center gap-2">
              <Search size={18} /> Start Searching
            </Link>
            <Link to="/documents" className="w-full sm:w-auto bg-surface border border-border text-primary-text px-8 py-3.5 rounded-md text-base font-medium hover:bg-gray-50 transition-colors flex items-center justify-center gap-2">
              <FileText size={18} /> Upload Documents
            </Link>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section id="features" className="py-24 px-6 bg-surface border-y border-border">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-primary-text mb-4">Built for Real Document Search</h2>
            <p className="text-secondary-text max-w-2xl mx-auto">DocSearch is built for accuracy and completeness. Every result comes from your actual documents — no hallucinations, no guesswork.</p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: Search,
                title: "Complete Page Search",
                desc: "Search across every page of your documents. If a term appears on 25 pages, DocSearch returns all 25 — never limited to top-3 results."
              },
              {
                icon: Shield,
                title: "Multi-Model AI Intelligence",
                desc: "Switch dynamically between Gemini, Tavily Web Intelligence, and OpenAlex to get the right answer for every research question."
              },
              {
                icon: Shield,
                title: "Evidence-Grounded AI",
                desc: "Ask natural language questions. DocSearch retrieves real evidence from your documents and uses AI to synthesize a grounded answer with page citations."
              },
              {
                icon: Lock,
                title: "Permission-Aware Search",
                desc: "Strict access controls ensure users only retrieve and analyze documents they are explicitly authorized to view."
              },
              {
                icon: CheckCircle2,
                title: "Strict Abstention",
                desc: "If the document doesn't contain enough evidence, DocSearch will not hallucinate. It explicitly abstains with a clear message."
              },
              {
                icon: LineChart,
                title: "Search Analytics",
                desc: "Track search activity, most searched terms, retrieval success rates, and document coverage on a dedicated dashboard."
              }
            ].map((f, i) => (
              <div key={i} className="p-8 border border-border rounded-xl bg-background hover:shadow-md transition-shadow group">
                <div className="w-12 h-12 bg-surface border border-border rounded-lg flex items-center justify-center mb-6 text-primary-accent group-hover:scale-110 transition-transform">
                  <f.icon size={24} />
                </div>
                <h3 className="text-lg font-bold text-primary-text mb-3">{f.title}</h3>
                <p className="text-sm text-secondary-text leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-auto py-12 px-6 border-t border-border bg-surface">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-secondary-text">
          <div className="flex items-center gap-2 font-bold text-primary-text">
            <div className="w-5 h-5 bg-primary-accent rounded flex items-center justify-center">
              <Search size={11} className="text-white" />
            </div>
            Doc<span className="text-primary-accent">Search</span>
          </div>
          <p>© 2026 DocSearch. All rights reserved.</p>
          <div className="flex items-center gap-6">
            <a href="#" className="hover:text-primary-text transition-colors">Privacy Policy</a>
            <a href="#" className="hover:text-primary-text transition-colors">Security</a>
            <a href="#" className="hover:text-primary-text transition-colors">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
