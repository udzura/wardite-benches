fn is_odd_prime(candidate: u32) -> bool {
    let mut divisor = 3u32;
    while u64::from(divisor) * u64::from(divisor) <= u64::from(candidate) {
        if candidate % divisor == 0 {
            return false;
        }
        divisor += 2;
    }
    true
}

#[unsafe(no_mangle)]
pub extern "C" fn count_primes(limit: u32) -> u32 {
    let odd_primes = (3..=limit)
        .step_by(2)
        .filter(|&candidate| is_odd_prime(candidate))
        .count();
    u32::from(limit >= 2) + odd_primes as u32
}

#[unsafe(no_mangle)]
pub extern "C" fn count_primes_sieve(limit: u32) -> u32 {
    if limit < 2 {
        return 0;
    }

    // One byte per odd candidate. Index i represents 2*i + 3.
    let mut composite = vec![0u8; ((limit - 1) / 2) as usize];
    for prime in (3..=limit).step_by(2) {
        let square = u64::from(prime) * u64::from(prime);
        if square > u64::from(limit) {
            break;
        }
        if composite[((prime - 3) / 2) as usize] == 0 {
            // Consecutive odd multiples differ by 2*prime in value.
            let start = ((square - 3) / 2) as usize;
            for index in (start..composite.len()).step_by(prime as usize) {
                composite[index] = 1;
            }
        }
    }

    1 + composite.iter().filter(|&&marked| marked == 0).count() as u32
}
