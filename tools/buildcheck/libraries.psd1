# A throwaway chain, for tools\check_build.ps1: cbmid uses cbbase.
@{
	Libraries = @(
		@{ Name = 'cbbase'; Folder = 'libs\base'; Uses = @() }
		@{ Name = 'cbmid'; Folder = 'libs\mid'; Uses = @('cbbase') }
	)
}
