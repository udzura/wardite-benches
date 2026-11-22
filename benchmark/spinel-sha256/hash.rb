require "digest"
data = File.binread(ARGV.fetch(0))
expected = ["cb740da111ff6ef951f51fac3296466777cc7b9b48d327f8d8089edeae71a7a4"].pack("H*")
33.times do |i|
  t = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  digest = Digest::SHA256.digest(data)
  elapsed = Process.clock_gettime(Process::CLOCK_MONOTONIC) - t
  raise "digest mismatch" unless digest == expected
  puts(elapsed * 1000.0) if i > 0
end
