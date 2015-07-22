\documentclass[%
	((( __language ))),%
	((* if showsolutions *))showsolutions((* endif *)),%
	((* if showsummary *))showsummary((* endif *)),%
]{cms-contest}

\usepackage[((( fontenc )))]{fontenc}
\usepackage[((( inputenc )))]{inputenc}
\usepackage[((( __language )))]{babel}

((* for __package in __additional_packages *))
	((( __package )))
((* endfor *))

\begin{document}
	\begin{contest}{(((description)))}{(((location)))}{(((date)))}
		\setContestLogo{(((logo)))}
		((* for __problem in __problems *))
			((( __problem )))
		((* endfor *))
	\end{contest}
\end{document}