# The libraries build.ps1 knows about. A library comes after everything in its Uses.
# Its main file is Folder\Name.phi, and programs include it with `use Name;`.
@{
	Libraries = @(
		@{ Name = 'corelib'; Folder = 'libs\core'; Uses = @() }
		@{ Name = 'weblib'; Folder = 'libs\web'; Uses = @() }
	)
}
