import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'polymarket.com',
        pathname: '/images/**',
      },
      {
        protocol: 'https',
        hostname: 'polymarket-upload.s3.us-east-2.amazonaws.com',
        pathname: '/**',
      },
    ],
  },
  // Proxy API requests to FastAPI backend in development
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: process.env.API_URL || 'http://localhost:8000/api/v1/:path*',
      },
    ];
  },
};

export default nextConfig;
