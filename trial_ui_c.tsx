import React, { useState, useEffect } from 'react';
import { Send, User, FileText, Clock, ChevronLeft, ChevronRight, Sparkles, LogIn, LogOut, Menu } from 'lucide-react';

export default function PoliticalTransparencyUI() {
  const [chatMessages, setChatMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isChatExpanded, setIsChatExpanded] = useState(true);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [showLogin, setShowLogin] = useState(false);
  const [userData, setUserData] = useState(null);
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [signupName, setSignupName] = useState('');
  const [signupEmail, setSignupEmail] = useState('');
  const [signupPassword, setSignupPassword] = useState('');
  const [isSignup, setIsSignup] = useState(false);

  // Load user data from storage on mount
  useEffect(() => {
    loadUserData();
  }, []);

  const loadUserData = async () => {
    try {
      const sessionResult = await window.storage.get('current_session', false);
      if (sessionResult?.value) {
        const session = JSON.parse(sessionResult.value);
        const userResult = await window.storage.get(`user:${session.userId}`, false);
        if (userResult?.value) {
          const user = JSON.parse(userResult.value);
          setUserData(user);
          setIsLoggedIn(true);
        }
      }
    } catch (error) {
      console.log('No active session');
    }
  };

  const handleLogin = async () => {
    try {
      // Check if user exists
      const userListResult = await window.storage.list('user:', false);
      if (!userListResult?.keys) {
        alert('No account found. Please sign up.');
        return;
      }

      // Find user with matching email
      for (const key of userListResult.keys) {
        try {
          const userResult = await window.storage.get(key, false);
          if (userResult?.value) {
            const user = JSON.parse(userResult.value);
            if (user.email === loginEmail && user.password === loginPassword) {
              setUserData(user);
              setIsLoggedIn(true);
              await window.storage.set('current_session', JSON.stringify({ userId: user.id }), false);
              setShowLogin(false);
              setLoginEmail('');
              setLoginPassword('');
              return;
            }
          }
        } catch (e) {
          continue;
        }
      }
      
      alert('Invalid email or password');
    } catch (error) {
      console.error('Login error:', error);
      alert('Login failed. Please try again.');
    }
  };

  const handleSignup = async () => {
    if (!signupName || !signupEmail || !signupPassword) {
      alert('Please fill in all fields');
      return;
    }

    try {
      const userId = `user_${Date.now()}`;
      const newUser = {
        id: userId,
        name: signupName,
        email: signupEmail,
        password: signupPassword,
        createdAt: new Date().toISOString()
      };

      await window.storage.set(`user:${userId}`, JSON.stringify(newUser), false);
      await window.storage.set('current_session', JSON.stringify({ userId }), false);
      
      setUserData(newUser);
      setIsLoggedIn(true);
      setShowLogin(false);
      setSignupName('');
      setSignupEmail('');
      setSignupPassword('');
      setIsSignup(false);
    } catch (error) {
      console.error('Signup error:', error);
      alert('Signup failed. Please try again.');
    }
  };

  const handleLogout = async () => {
    try {
      await window.storage.delete('current_session', false);
      setIsLoggedIn(false);
      setUserData(null);
      setChatMessages([]);
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const handleSendMessage = () => {
    if (inputMessage.trim()) {
      setChatMessages([...chatMessages, { type: 'user', text: inputMessage }]);
      setInputMessage('');
      
      setTimeout(() => {
        setChatMessages(prev => [...prev, { 
          type: 'assistant', 
          text: `I'm Relay, your political transparency assistant. How can I help you understand this better?` 
        }]);
      }, 1000);
    }
  };

  const suggestedQuestions = [
    "What bills did they vote on?",
    "Compare promises vs actions",
    "How do I contact them?",
    "Show recent updates"
  ];

  const mockStories = [
    {
      id: 1,
      title: "Infrastructure Bill Vote Analysis",
      representative: "Sen. Jane Smith",
      alignment: 87,
      category: "Economy",
      summary: "Voted in favor of infrastructure spending, consistent with campaign promises on job creation.",
      timestamp: "2 hours ago"
    },
    {
      id: 2,
      title: "Healthcare Reform Statement",
      representative: "Rep. John Doe",
      alignment: 65,
      category: "Healthcare",
      summary: "Public statements support expansion, but recent committee votes show mixed record.",
      timestamp: "5 hours ago"
    },
    {
      id: 3,
      title: "Climate Policy Update",
      representative: "Sen. Maria Garcia",
      alignment: 92,
      category: "Environment",
      summary: "Strong alignment between campaign promises and legislative actions on renewable energy.",
      timestamp: "1 day ago"
    },
    {
      id: 4,
      title: "Education Funding Vote",
      representative: "Rep. Michael Chen",
      alignment: 78,
      category: "Education",
      summary: "Supported increased education funding, aligning with campaign trail commitments.",
      timestamp: "2 days ago"
    }
  ];

  return (
    <div className="flex h-screen bg-black text-white overflow-hidden">
      {/* User Profile Button */}
      <div className="fixed top-4 left-4 z-50">
        {isLoggedIn ? (
          <div className="flex items-center space-x-3 bg-gradient-to-r from-purple-900/80 to-purple-800/80 backdrop-blur-xl px-4 py-2 rounded-full border border-purple-600/40 shadow-lg shadow-purple-500/20">
            <div className="w-8 h-8 bg-gradient-to-br from-purple-400 to-pink-500 rounded-full flex items-center justify-center font-bold text-sm">
              {userData?.name?.charAt(0).toUpperCase()}
            </div>
            <span className="text-sm font-medium text-white">{userData?.name}</span>
            <button
              onClick={handleLogout}
              className="ml-2 p-1 hover:bg-purple-700/50 rounded-full transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <button
            onClick={() => setShowLogin(true)}
            className="flex items-center space-x-2 bg-gradient-to-r from-purple-900/80 to-purple-800/80 backdrop-blur-xl px-4 py-2 rounded-full border border-purple-600/40 shadow-lg shadow-purple-500/20 hover:shadow-purple-500/40 transition-all"
          >
            <LogIn className="w-4 h-4" />
            <span className="text-sm font-medium">Sign In</span>
          </button>
        )}
      </div>

      {/* Login Modal */}
      {showLogin && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-gradient-to-br from-purple-950 to-black border border-purple-600/40 rounded-2xl p-6 max-w-md w-full shadow-2xl shadow-purple-500/20">
            <h2 className="text-2xl font-bold mb-6 bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
              {isSignup ? 'Create Account' : 'Welcome Back'}
            </h2>
            
            {isSignup && (
              <div className="mb-4">
                <label className="block text-sm font-medium text-purple-300 mb-2">Name</label>
                <input
                  type="text"
                  value={signupName}
                  onChange={(e) => setSignupName(e.target.value)}
                  className="w-full px-4 py-2 bg-purple-900/30 border border-purple-600/40 rounded-lg text-white placeholder-purple-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  placeholder="Your name"
                />
              </div>
            )}
            
            <div className="mb-4">
              <label className="block text-sm font-medium text-purple-300 mb-2">Email</label>
              <input
                type="email"
                value={isSignup ? signupEmail : loginEmail}
                onChange={(e) => isSignup ? setSignupEmail(e.target.value) : setLoginEmail(e.target.value)}
                className="w-full px-4 py-2 bg-purple-900/30 border border-purple-600/40 rounded-lg text-white placeholder-purple-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                placeholder="you@example.com"
              />
            </div>
            
            <div className="mb-6">
              <label className="block text-sm font-medium text-purple-300 mb-2">Password</label>
              <input
                type="password"
                value={isSignup ? signupPassword : loginPassword}
                onChange={(e) => isSignup ? setSignupPassword(e.target.value) : setLoginPassword(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && (isSignup ? handleSignup() : handleLogin())}
                className="w-full px-4 py-2 bg-purple-900/30 border border-purple-600/40 rounded-lg text-white placeholder-purple-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                placeholder="••••••••"
              />
            </div>
            
            <button
              onClick={isSignup ? handleSignup : handleLogin}
              className="w-full py-3 bg-gradient-to-r from-purple-600 to-pink-600 rounded-lg font-semibold hover:from-purple-700 hover:to-pink-700 transition-all shadow-lg shadow-purple-500/30"
            >
              {isSignup ? 'Sign Up' : 'Sign In'}
            </button>
            
            <button
              onClick={() => setIsSignup(!isSignup)}
              className="w-full mt-3 text-sm text-purple-400 hover:text-purple-300"
            >
              {isSignup ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
            </button>
            
            <button
              onClick={() => setShowLogin(false)}
              className="w-full mt-2 text-sm text-gray-500 hover:text-gray-400"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="bg-gradient-to-r from-purple-950 via-purple-900 to-black border-b border-purple-700/30 px-6 py-3.5 shadow-lg">
          <div className="flex items-center justify-center space-x-3">
            <div className="w-9 h-9 bg-gradient-to-br from-purple-500 to-pink-600 rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/30">
              <FileText className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-white to-purple-200 bg-clip-text text-transparent">
                Political Transparency
              </h1>
              <p className="text-xs text-purple-300">Track what they say vs. what they do</p>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto px-6 py-6 bg-gradient-to-br from-black via-purple-950/10 to-black">
          <div className="max-w-4xl mx-auto">
            {/* Welcome Section */}
            <div className="mb-8 animate-fade-in">
              <div className="flex items-center space-x-3 mb-3">
                <Sparkles className="w-7 h-7 text-purple-400 animate-pulse" />
                <h2 className="text-4xl font-bold bg-gradient-to-r from-purple-400 via-pink-400 to-purple-500 bg-clip-text text-transparent">
                  Hey {isLoggedIn && userData?.name ? userData.name : 'there'}!
                </h2>
              </div>
              <p className="text-lg text-gray-300 ml-10">
                Here are some interesting stories for you today
              </p>
            </div>

            {/* Filter Tabs */}
            <div className="flex space-x-2 mb-6 overflow-x-auto pb-2 scrollbar-hide">
              {['All', 'Economy', 'Healthcare', 'Environment', 'Education', 'Justice'].map((category) => (
                <button
                  key={category}
                  className={`px-4 py-2 rounded-xl text-sm font-semibold whitespace-nowrap transition-all ${
                    category === 'All' 
                      ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white shadow-lg shadow-purple-500/40' 
                      : 'bg-purple-900/20 text-purple-300 hover:bg-purple-800/30 border border-purple-700/30'
                  }`}
                >
                  {category}
                </button>
              ))}
            </div>

            {/* News Feed */}
            <div className="space-y-4">
              {mockStories.map((story, idx) => (
                <div
                  key={story.id}
                  className="bg-gradient-to-br from-purple-950/40 via-purple-900/20 to-black/60 backdrop-blur-md rounded-2xl border border-purple-700/30 p-5 hover:border-purple-500/50 hover:shadow-xl hover:shadow-purple-500/10 transition-all cursor-pointer"
                  style={{ animationDelay: `${idx * 100}ms` }}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center space-x-3">
                      <div className="w-11 h-11 bg-gradient-to-br from-purple-500 to-pink-600 rounded-full flex items-center justify-center shadow-lg">
                        <User className="w-5 h-5 text-white" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-white">{story.representative}</h3>
                        <div className="flex items-center space-x-1.5 text-xs text-gray-400">
                          <Clock className="w-3 h-3" />
                          <span>{story.timestamp}</span>
                        </div>
                      </div>
                    </div>
                    <span className="px-3 py-1.5 bg-purple-500/20 text-purple-300 rounded-full text-xs font-semibold border border-purple-500/40">
                      {story.category}
                    </span>
                  </div>

                  <h4 className="text-lg font-bold text-white mb-2">{story.title}</h4>
                  <p className="text-sm text-gray-300 mb-4 leading-relaxed">{story.summary}</p>

                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <span className="text-xs font-medium text-gray-400">Alignment:</span>
                      <div className="flex items-center space-x-2">
                        <div className="w-28 h-2 bg-gray-800/50 rounded-full overflow-hidden backdrop-blur-sm">
                          <div 
                            className={`h-full rounded-full transition-all ${
                              story.alignment >= 80 ? 'bg-gradient-to-r from-green-500 to-emerald-400' :
                              story.alignment >= 60 ? 'bg-gradient-to-r from-yellow-500 to-orange-400' : 
                              'bg-gradient-to-r from-red-500 to-pink-500'
                            }`}
                            style={{ width: `${story.alignment}%` }}
                          />
                        </div>
                        <span className="text-sm font-bold text-white">{story.alignment}%</span>
                      </div>
                    </div>
                    <button className="text-purple-400 hover:text-purple-300 font-semibold text-sm transition-colors">
                      View Details →
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Load More */}
            <div className="text-center mt-8">
              <button className="px-6 py-3 bg-purple-900/20 border border-purple-700/30 text-purple-300 rounded-xl font-semibold hover:bg-purple-800/30 transition-all">
                Load More Stories
              </button>
            </div>
          </div>
        </main>
      </div>

      {/* Chat Sidebar - Relay */}
      <div 
        className={`bg-gradient-to-b from-purple-950/95 via-black to-black/95 backdrop-blur-xl border-l border-purple-700/30 flex flex-col transition-all duration-300 ease-in-out shadow-2xl ${
          isChatExpanded ? 'w-80' : 'w-0'
        }`}
      >
        {isChatExpanded && (
          <>
            {/* Chat Header */}
            <div className="px-5 py-4 border-b border-purple-700/30 bg-gradient-to-r from-purple-900/50 to-transparent">
              <div className="flex items-center space-x-2 mb-1">
                <Sparkles className="w-5 h-5 text-purple-400" />
                <h3 className="font-bold text-white">Relay</h3>
              </div>
              <p className="text-xs text-purple-300">Your AI transparency assistant</p>
            </div>

            {/* Suggested Questions */}
            {chatMessages.length === 0 && (
              <div className="px-5 py-4 space-y-2">
                <p className="text-xs font-semibold text-purple-400 mb-3">SUGGESTED QUESTIONS</p>
                {suggestedQuestions.map((question, idx) => (
                  <button
                    key={idx}
                    onClick={() => setInputMessage(question)}
                    className="w-full text-left px-3 py-2.5 bg-purple-900/20 hover:bg-purple-800/30 rounded-xl text-xs text-purple-200 transition-all border border-purple-700/30 hover:border-purple-600/50"
                  >
                    {question}
                  </button>
                ))}
              </div>
            )}

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
              {chatMessages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] px-3 py-2.5 rounded-xl ${
                      msg.type === 'user'
                        ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white shadow-lg'
                        : 'bg-purple-900/40 text-purple-100 border border-purple-700/40'
                    }`}
                  >
                    <p className="text-xs leading-relaxed">{msg.text}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Chat Input */}
            <div className="px-5 py-4 border-t border-purple-700/30 bg-gradient-to-r from-transparent to-purple-900/30">
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                  placeholder="Ask Relay anything..."
                  className="flex-1 px-4 py-2.5 bg-purple-900/30 border border-purple-700/40 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent text-white placeholder-purple-400 text-sm"
                />
                <button
                  onClick={handleSendMessage}
                  className="p-2.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-xl hover:from-purple-700 hover:to-pink-700 transition-all shadow-lg shadow-purple-500/30"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Toggle Chat Button */}
      <button
        onClick={() => setIsChatExpanded(!isChatExpanded)}
        className="fixed right-4 bottom-6 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 p-4 rounded-full shadow-2xl shadow-purple-500/40 transition-all z-40 hover:scale-110"
      >
        {isChatExpanded ? <ChevronRight className="w-5 h-5" /> : <Sparkles className="w-5 h-5" />}
      </button>
    </div>
  );
}
