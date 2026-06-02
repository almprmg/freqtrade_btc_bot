# Calendar Effects on BTC/USDT 2018-2026

Analyzed: 2340 daily returns

## Significant patterns (p < 0.05)

        dimension                  group    n  mean_pct  median_pct  hit_rate  std_pct  t_stat  p_value  significant
            Month                October  186  0.540276    0.335089  0.553763 2.373881   3.096   0.0023         True
Days-from-Halving   90-365d (Early bull)  550  0.387703    0.173779  0.532727 3.302161   2.751   0.0061         True
      Day-of-Week              Wednesday  334  0.490558    0.206297  0.523952 3.458030   2.589   0.0101         True
      Quarter-End             Other days 2177  0.152937    0.045393  0.509417 3.251697   2.194   0.0283         True
      Day-of-Week                 Monday  334  0.451168    0.198898  0.526946 3.829314   2.150   0.0323         True
Days-from-Halving >900d (Reaccumulation)  669  0.258468    0.031556  0.514200 3.325917   2.009   0.0450         True
     Day-of-Month            End (26-31)  416  0.277436   -0.080386  0.478365 2.854029   1.980   0.0483         True
            Month                   July  186  0.354087    0.100026  0.505376 2.425025   1.986   0.0485         True


## Day-of-Week
```
  dimension     group   n  mean_pct  median_pct  hit_rate  std_pct  t_stat  p_value  significant
Day-of-Week    Monday 334  0.451168    0.198898  0.526946 3.829314   2.150   0.0323         True
Day-of-Week   Tuesday 334  0.112421    0.012083  0.505988 2.928553   0.701   0.4841        False
Day-of-Week Wednesday 334  0.490558    0.206297  0.523952 3.458030   2.589   0.0101         True
Day-of-Week  Thursday 335 -0.211851   -0.222411  0.456716 3.964063  -0.977   0.3294        False
Day-of-Week    Friday 335  0.124467    0.045393  0.504478 3.309693   0.687   0.4924        False
Day-of-Week  Saturday 334  0.044206    0.063728  0.529940 1.845085   0.437   0.6622        False
Day-of-Week    Sunday 334  0.050651    0.043795  0.517964 2.434834   0.380   0.7045        False
```

## Month
```
dimension     group   n  mean_pct  median_pct  hit_rate  std_pct  t_stat  p_value  significant
    Month   January 216  0.300014    0.075967  0.537037 3.183552   1.382   0.1685        False
    Month  February 198  0.235831   -0.118821  0.464646 3.636851   0.910   0.3639        False
    Month     March 217  0.303524    0.251158  0.529954 4.719617   0.945   0.3456        False
    Month     April 210  0.134519    0.097254  0.528571 2.873751   0.677   0.4993        False
    Month       May 215 -0.132483    0.042763  0.502326 3.413387  -0.568   0.5708        False
    Month      June 180 -0.219568   -0.078514  0.477778 3.326904  -0.883   0.3784        False
    Month      July 186  0.354087    0.100026  0.505376 2.425025   1.986   0.0485         True
    Month    August 186 -0.109961   -0.191648  0.451613 2.715633  -0.551   0.5825        False
    Month September 180  0.024808    0.224508  0.538889 2.651279   0.125   0.9005        False
    Month   October 186  0.540276    0.335089  0.553763 2.373881   3.096   0.0023         True
    Month  November 180  0.228228   -0.029901  0.494444 3.272778   0.933   0.3521        False
    Month  December 186  0.136790    0.125723  0.521505 2.583676   0.720   0.4724        False
```

## Days-from-Halving
```
        dimension                   group   n  mean_pct  median_pct  hit_rate  std_pct  t_stat  p_value  significant
Days-from-Halving      0-90d post-halving 180  0.204181    0.121462  0.522222 2.567024   1.064   0.2887        False
Days-from-Halving    90-365d (Early bull) 550  0.387703    0.173779  0.532727 3.302161   2.751   0.0061         True
Days-from-Halving    365-540d (Parabolic) 350  0.161594    0.109217  0.525714 3.276661   0.921   0.3575        False
Days-from-Halving 540-700d (Distribution) 320 -0.218042   -0.111719  0.471875 3.028831  -1.286   0.1995        False
Days-from-Halving         700-900d (Bear) 271 -0.203671   -0.217540  0.464945 3.057690  -1.095   0.2747        False
Days-from-Halving  >900d (Reaccumulation) 669  0.258468    0.031556  0.514200 3.325917   2.009   0.0450         True
```

## Quarter-End
```
  dimension            group    n  mean_pct  median_pct  hit_rate  std_pct  t_stat  p_value  significant
Quarter-End Quarter-end week  163  0.132204    0.081091  0.509202 2.361479   0.713   0.4771        False
Quarter-End       Other days 2177  0.152937    0.045393  0.509417 3.251697   2.194   0.0283         True
```
